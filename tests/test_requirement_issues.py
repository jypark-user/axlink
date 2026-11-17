"""요구사항에 이어진 이슈·일감의 진행 (2026-11-17 사용자 지시, SWFR.WEB.002).

요구사항 화면에서 「근거 상태」 대신, 그 요구사항 코드를 참조한 이슈·일감이 몇 건 등록됐고 몇 건이
닫혔는지 본다. 용역사가 그 요구사항으로 일을 얼마나 하고 있는지 보는 지표이고, 이행률(검증·인수
상태로 센다)과는 따로다. 살아 있는 연결만 센다.
"""

import uuid

import pytest

from app.db import tx
from app.standard import trace_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_해결과_종료는_닫힘으로_센다():
    p = trace_service.issue_progress(["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED", "OPEN"])
    assert p.model_dump() == {"total": 5, "open": 2, "inProgress": 1, "closed": 2}
    assert trace_service.issue_progress([]).total == 0


# (상태, 연결 상태, 종류). 끊긴 연결과 대체된 연결은 세지 않는다
_ISSUES = [
    ("OPEN", "ACTIVE", "GENERAL"),
    ("IN_PROGRESS", "ACTIVE", "GENERAL"),
    ("CLOSED", "ACTIVE", "GENERAL"),
    ("RESOLVED", "ACTIVE", "DEFECT"),
    ("OPEN", "BROKEN", "GENERAL"),
    ("CLOSED", "SUPERSEDED", "GENERAL"),
]


@pytest.fixture
def linked():
    rid = str(uuid.uuid4())
    issue_ids = [str(uuid.uuid4()) for _ in _ISSUES]
    lonely = str(uuid.uuid4())
    with tx() as cur:
        for req, code in ((rid, "SWFR.TST.901"), (lonely, "SWFR.TST.902")):
            cur.execute(
                """
                insert into requirement (id, project_id, code, title, body, priority, status,
                                         evidence_status, source_kind)
                values (%s, %s, %s, '이슈 진행 시험', '', 'MUST', 'DEFINED', 'DEFINED', 'MANUAL')
                """,
                (req, PID, code),
            )
        pairs = zip(issue_ids, _ISSUES, strict=True)
        for n, (iid, (status, link_status, kind)) in enumerate(pairs):
            cur.execute(
                """
                insert into issue (id, project_id, title, status, issue_kind, issue_key)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (iid, PID, f"진행 시험 이슈 {n}", status, kind, f"GH-99{n}"),
            )
            cur.execute(
                """
                insert into trace_link (project_id, from_type, from_id, to_type, to_id, link_kind,
                                        status, evidence_kind)
                values (%s, 'ISSUE', %s, 'REQUIREMENT', %s, 'IMPLEMENTS', %s, 'TEXT_REQ_CODE')
                """,
                (PID, iid, rid, link_status),
            )
    yield {"rid": rid, "lonely": lonely}
    with tx() as cur:
        cur.execute("delete from trace_link where to_id = %s", (rid,))
        cur.execute("delete from issue where id = any(%s::uuid[])", (issue_ids,))
        cur.execute("delete from requirement where id = any(%s::uuid[])", ([rid, lonely],))


@requires_db
def test_목록과_상세가_같은_수로_진행을_보인다(client, client_token, linked):
    token = client_token("r2")
    res = client.get(
        f"/api/projects/{PID}/traceability?size=200&q=SWFR.TST.90", headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    rows = {r["requirementCode"]: r for r in res.json()["content"]}
    expected = {"total": 4, "open": 1, "inProgress": 1, "closed": 2}
    assert rows["SWFR.TST.901"]["issueProgress"] == expected
    assert rows["SWFR.TST.902"]["issueProgress"]["total"] == 0  # 등록된 이슈 없음

    detail = client.get(
        f"/api/projects/{PID}/requirements/{linked['rid']}", headers=_auth(token)
    ).json()
    assert detail["issueProgress"] == expected
    # 진행 → 열림 → 해결·종료 순, 끊기거나 대체된 연결은 없다
    assert [i["status"] for i in detail["issues"]] == ["IN_PROGRESS", "OPEN", "RESOLVED", "CLOSED"]
    assert {i["kind"] for i in detail["issues"]} == {"GENERAL", "DEFECT"}
