"""요구사항 상태 지정 (SWFR.PIP.008, ARC-025).

기본은 근거대로 움직인다. 발주기관은 사유와 함께 어느 상태로든 지정할 수 있고, 수집이 다시
돌아도 지정은 남는다. 지정을 거두면 근거 상태로 돌아간다. 이행률·요약·추적표가 같은 값을 쓴다.
"""

import uuid

import pytest

from app.db import fetch_all, fetch_one, tx
from app.rag import entity_table
from app.standard import repository
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def gh_requirement():
    """예전에 GitHub 이슈로 만든 열린 요구사항 하나(ARC-030 전)."""
    with tx() as cur:
        org = fetch_one(cur, "select id from organization where type = 'CONTRACTOR' limit 1")
        conn_id = str(uuid.uuid4())
        cur.execute(
            """
            insert into tool_connection (id, project_id, contractor_org_id, tool, name, base_url,
                                         target_resource, auth_encrypted, auth_hint, status)
            values (%s, %s, %s, 'GITHUB', 'TST', 'https://api.github.invalid/',
                    'decision/test', 'x', 'x', 'ACTIVE')
            """,
            (conn_id, PID, org["id"]),
        )
        rec = _rec("DEFINED")
        rid = str(fetch_one(
            cur,
            """
            insert into requirement (project_id, title, body, priority, status, evidence_status,
                                     tool_connection_id, external_id, external_url, source_kind)
            values (%s, %s, %s, %s, %s, %s, %s, 'issue:9301', %s, 'TOOL') returning id
            """,
            (PID, rec["title"], rec["body"], rec["priority"], rec["status"], rec["status"],
             conn_id, rec["external_url"]),
        )["id"])
    yield {"id": rid, "connection": conn_id}
    with tx() as cur:
        cur.execute("delete from activity_event where target_key = %s", (rid,))
        cur.execute("delete from requirement where id = %s", (rid,))
        cur.execute("delete from tool_connection where id = %s", (conn_id,))


def _rec(status: str) -> dict:
    return {
        "code": None, "title": "지정 시험 요구사항", "body": "", "priority": "MUST",
        "status": status, "assignee": None, "source_created_at": None,
        "source_updated_at": None, "external_url": "https://github.invalid/i/9301",
    }


def _resync(conn_id: str, status: str) -> None:
    """수집이 다시 돌아 출처 이슈의 열림·닫힘을 읽는다(service.promote_connection 과 같은 길)."""
    with tx() as cur:
        own = repository.find_requirement_by_source(cur, conn_id, "issue:9301")
        repository.update_requirement_evidence(
            cur, str(own["id"]), conn_id, "issue:9301", _rec(status)
        )


def _row(rid: str) -> dict:
    with tx() as cur:
        return fetch_one(
            cur,
            "select status, evidence_status, decided_status, decided_reason from requirement "
            "where id = %s",
            (rid,),
        )


@requires_db
def test_발주기관이_사유와_함께_지정하면_지금_상태가_바뀌고_근거는_남는다(
    client, client_token, gh_requirement
):
    rid = gh_requirement["id"]
    res = client.put(
        f"/api/projects/{PID}/requirements/{rid}/status",
        json={"status": "VERIFIED", "reason": "시연에서 근거 게이트 동작을 확인함"},
        headers=_auth(client_token("r2")),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "VERIFIED"
    assert body["evidenceStatus"] == "DEFINED"
    assert body["statusBasis"] == "CLIENT_DECIDED"
    assert body["decision"]["reason"] == "시연에서 근거 게이트 동작을 확인함"
    assert body["decision"]["decidedAt"]
    fields = {h["field"] for h in body["history"]}
    assert {"status", "status_decision"} <= fields

    with tx() as cur:
        ev = fetch_one(
            cur, "select kind, audience from activity_event where target_key = %s", (rid,)
        )
    assert ev["kind"] == "REQUIREMENT_STATUS_DECIDED" and ev["audience"] == "CONTRACTOR"


@requires_db
def test_수집이_다시_돌아도_지정은_남고_근거만_바뀐다(client, client_token, gh_requirement):
    rid, conn = gh_requirement["id"], gh_requirement["connection"]
    client.put(
        f"/api/projects/{PID}/requirements/{rid}/status",
        json={"status": "ACCEPTED", "reason": "인수 확인"},
        headers=_auth(client_token("r2")),
    ).raise_for_status()

    _resync(conn, "IMPLEMENTED")  # 출처 이슈가 닫혔다
    row = _row(rid)
    assert row["status"] == "ACCEPTED"
    assert row["evidence_status"] == "IMPLEMENTED"


@requires_db
def test_되돌리면_근거_상태로_돌아가고_그_뒤로는_근거대로_움직인다(
    client, client_token, gh_requirement
):
    rid, conn = gh_requirement["id"], gh_requirement["connection"]
    token = client_token("r2")
    client.put(
        f"/api/projects/{PID}/requirements/{rid}/status",
        json={"status": "REJECTED", "reason": "범위 밖으로 판단"},
        headers=_auth(token),
    ).raise_for_status()
    _resync(conn, "IMPLEMENTED")

    res = client.post(
        f"/api/projects/{PID}/requirements/{rid}/status/revert",
        json={"reason": "판단 철회"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "IMPLEMENTED"
    assert res.json()["decision"] is None
    assert res.json()["statusBasis"] == "SOURCE_ISSUE_CLOSED"

    _resync(conn, "DEFINED")  # 출처 이슈를 다시 열었다
    assert _row(rid)["status"] == "DEFINED"

    again = client.post(
        f"/api/projects/{PID}/requirements/{rid}/status/revert",
        json={"reason": "다시"},
        headers=_auth(token),
    )
    assert again.status_code == 409


@requires_db
def test_용역사는_지정할_수_없고_사유가_없거나_모르는_상태면_거절한다(
    client, client_token, gh_requirement
):
    rid = gh_requirement["id"]
    url = f"/api/projects/{PID}/requirements/{rid}/status"

    by_contractor = client.put(
        url, json={"status": "VERIFIED", "reason": "자체 확인"},
        headers=_auth(client_token("r3")),
    )
    assert by_contractor.status_code == 403

    client_auth = _auth(client_token("r2"))
    assert client.put(url, json={"status": "VERIFIED", "reason": ""},
                      headers=client_auth).status_code == 400
    assert client.put(url, json={"status": "VERIFIED", "reason": "   "},
                      headers=client_auth).status_code == 400
    assert client.put(url, json={"status": "DONE", "reason": "x"},
                      headers=client_auth).status_code == 400
    assert _row(rid)["decided_status"] is None


@requires_db
def test_다른_사업의_요구사항은_없는_것으로_본다(client, client_token, gh_requirement):
    other = str(uuid.uuid4())
    res = client.put(
        f"/api/projects/{PID}/requirements/{other}/status",
        json={"status": "VERIFIED", "reason": "x"},
        headers=_auth(client_token("r2")),
    )
    assert res.status_code == 404


@requires_db
def test_지정한_상태가_요약_이행률_AI_표에_같이_쓰인다(client, client_token, gh_requirement):
    rid = gh_requirement["id"]
    token = client_token("r2")
    before = client.get(f"/api/projects/{PID}/requirements/summary", headers=_auth(token)).json()

    client.put(
        f"/api/projects/{PID}/requirements/{rid}/status",
        json={"status": "VERIFIED", "reason": "검증 확인"},
        headers=_auth(token),
    ).raise_for_status()

    after = client.get(f"/api/projects/{PID}/requirements/summary", headers=_auth(token)).json()
    assert after["verified"] == before["verified"] + 1
    assert after["decided"] == before["decided"] + 1

    trace = client.get(
        f"/api/projects/{PID}/traceability?verified=true&size=200", headers=_auth(token)
    ).json()
    row = next(r for r in trace["content"] if r["requirementId"] == rid)
    assert row["requirementDecision"]["status"] == "VERIFIED"
    assert row["requirementEvidenceStatus"] == "DEFINED"

    with tx() as cur:
        counts = fetch_all(
            cur,
            "select count(*) filter (where status in ('VERIFIED','ACCEPTED')) as v "
            "from requirement where project_id = %s",
            (PID,),
        )[0]
        table = entity_table.build(cur, "REQUIREMENT", entity_table.ALL, [PID], 500)
    assert counts["v"] == after["verified"]
    status = {r.values["title"]: r.values["status"] for r in table.data.rows}
    assert status["지정 시험 요구사항"] == "VERIFIED(발주기관 지정)"
