"""요구사항 상태의 출처 표시 (SWFR.WEB.001).

GitHub 이슈를 닫으면 요구사항이 IMPLEMENTED 가 된다(mapping.to_requirement). 그건 원천 이슈가
닫혔다는 사실이지 구현·검증을 확인했다는 뜻이 아니다. 화면과 AI 표가 그 사실대로 부르는지,
그리고 다른 출처의 같은 상태까지 GitHub 닫힘으로 부르지 않는지 본다.
"""

import uuid

import pytest

from app.db import fetch_one, tx
from app.rag import entity_table
from app.standard import mapping
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_GitHub_닫힘에서_온_IMPLEMENTED_만_짚는다():
    assert mapping.requirement_status_basis("IMPLEMENTED", "GITHUB") == "SOURCE_ISSUE_CLOSED"
    assert mapping.requirement_status_basis("DEFINED", "GITHUB") is None
    assert mapping.requirement_status_basis("VERIFIED", "GITHUB") is None
    assert mapping.requirement_status_basis("IMPLEMENTED", "REDMINE") is None
    assert mapping.requirement_status_basis("IMPLEMENTED", None) is None


@pytest.fixture
def mixed_requirements():
    """GitHub 에서 닫힌 것, 수기로 IMPLEMENTED 인 것, GitHub 에서 열린 것."""
    with tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn_id = str(uuid.uuid4())
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'GITHUB', 'TST', 'https://api.github.invalid/',
                    'basis/test', 'x', 'x', 'ACTIVE')
            """,
            (conn_id, PID, org["id"]),
        )
        ids = {}
        for name, status, conn, ext in (
            ("gh_closed", "IMPLEMENTED", conn_id, "9101"),
            ("gh_open", "DEFINED", conn_id, "9102"),
            ("manual", "IMPLEMENTED", None, None),
        ):
            ids[name] = str(
                fetch_one(
                    cur,
                    """
                    insert into requirement (project_id, code, title, status, tool_connection_id,
                                             external_id, source_kind)
                    values (%s, null, %s, %s, %s, %s, %s)
                    returning id
                    """,
                    (PID, f"출처 시험 {name}", status, conn, ext, "TOOL" if conn else "MANUAL"),
                )["id"]
            )
    yield ids
    with tx() as cur:
        cur.execute("delete from requirement where id = any(%s::uuid[])", (list(ids.values()),))
        cur.execute("delete from tool_connection where id = %s", (conn_id,))


@requires_db
def test_요구사항_목록_추적표_상세가_같은_출처를_말한다(client, client_token, mixed_requirements):
    token = client_token("r2")
    ids = mixed_requirements
    expected = {ids["gh_closed"]: "SOURCE_ISSUE_CLOSED", ids["gh_open"]: None, ids["manual"]: None}

    listed = client.get(f"/api/projects/{PID}/requirements?size=200", headers=_auth(token))
    assert listed.status_code == 200, listed.text
    got = {r["id"]: r["statusBasis"] for r in listed.json()["content"] if r["id"] in expected}
    assert got == expected

    trace = client.get(f"/api/projects/{PID}/traceability?size=200", headers=_auth(token))
    assert trace.status_code == 200, trace.text
    got = {
        r["requirementId"]: r["requirementStatusBasis"]
        for r in trace.json()["content"]
        if r["requirementId"] in expected
    }
    assert got == expected

    for rid, basis in expected.items():
        detail = client.get(f"/api/projects/{PID}/requirements/{rid}", headers=_auth(token))
        assert detail.status_code == 200, detail.text
        assert detail.json()["statusBasis"] == basis
        # 내부 상태는 그대로다. 이행률 산식이 읽는 값이 바뀌지 않는다
        assert detail.json()["status"] in ("IMPLEMENTED", "DEFINED")


@requires_db
def test_AI_요구사항_표도_GitHub_닫힘만_그렇게_부른다(mixed_requirements):
    with tx() as cur:
        table = entity_table.build(cur, "REQUIREMENT", entity_table.ALL, [PID], 500)
    assert table is not None
    status = {r.values["title"]: r.values["status"] for r in table.data.rows}
    assert status["출처 시험 gh_closed"] == "원천 이슈 닫힘(구현·검증 완료를 뜻하지 않음)"
    assert status["출처 시험 manual"] == "IMPLEMENTED"
    assert status["출처 시험 gh_open"] == "DEFINED"
