"""요구사항 조회. GitHub 이슈에서 승격된 것이 이 API 로 화면에 뜬다."""

import uuid

import pytest

from app.db import tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded():
    """수기 요구사항 2건을 넣고 끝나면 지운다. 도구 연결 없이도 조회가 도는지 본다."""
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    with tx() as cur:
        for rid, code, title, priority in (
            (ids[0], "SWFR.TST.001", "첫 요구사항", "MUST"),
            (ids[1], "SWFR.TST.002", "둘째 요구사항", "SHOULD"),
        ):
            cur.execute(
                """
                insert into requirement (id, project_id, code, title, priority, status)
                values (%s, %s, %s, %s, %s, 'DEFINED')
                """,
                (rid, PID, code, title, priority),
            )
    yield ids
    with tx() as cur:
        cur.execute("delete from requirement where id = any(%s::uuid[])", (ids,))


@requires_db
def test_list_returns_seeded_requirements(client, client_token, seeded):
    body = client.get(
        f"/api/projects/{PID}/requirements?page=0&size=100", headers=_auth(client_token("r3"))
    ).json()
    codes = [r["code"] for r in body["content"]]
    assert "SWFR.TST.001" in codes and "SWFR.TST.002" in codes

    first = next(r for r in body["content"] if r["code"] == "SWFR.TST.001")
    assert first["title"] == "첫 요구사항"
    assert first["priority"] == "MUST"
    assert first["status"] == "DEFINED"
    # 도구에서 오지 않았으므로 수기다 — SWFR.PIP.002 의 원천 보존.
    assert first["source"]["tool"] == "MANUAL"
    assert first["traceComplete"] is False


@requires_db
def test_search_matches_code_or_title(client, client_token, seeded):
    by_code = client.get(
        f"/api/projects/{PID}/requirements?q=TST.002", headers=_auth(client_token("r3"))
    ).json()
    assert [r["code"] for r in by_code["content"]] == ["SWFR.TST.002"]

    by_title = client.get(
        f"/api/projects/{PID}/requirements?q=둘째", headers=_auth(client_token("r3"))
    ).json()
    assert [r["code"] for r in by_title["content"]] == ["SWFR.TST.002"]


@requires_db
def test_other_project_is_denied(client, client_token):
    other = "c0000000-0000-4000-8000-000000000099"
    res = client.get(f"/api/projects/{other}/requirements", headers=_auth(client_token("r3")))
    assert res.status_code == 403
