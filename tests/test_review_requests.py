"""확인 요청 → 조치 보고 → 확인완료 (SWFR.WEB.004~006).

발주기관(r2)이 요청하고 확인한다. 용역사(r3)가 보고한다. 요청 시점 상태를 떠 두고
보고 때 지금 상태와 나란히 놓는다.
"""

import pytest

from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def issue_target():
    """요청을 걸 이슈 하나. 끝나면 요청과 이슈를 지운다."""
    with tx() as cur:
        issue_id = fetch_one(
            cur,
            """
            insert into issue (project_id, issue_key, title, status, severity, source_kind)
            values (%s, 'GH-8001', '확인 요청 시험 이슈', 'OPEN', 'MAJOR', 'MANUAL')
            returning id
            """,
            (PID,),
        )["id"]
    yield str(issue_id)
    with tx() as cur:
        cur.execute("delete from review_request where project_id = %s", (PID,))
        cur.execute("delete from issue where id = %s", (issue_id,))


@requires_db
def test_targets_come_from_standard_model(client, client_token):
    token = client_token("r2")
    products = client.get(
        f"/api/projects/{PID}/review-targets?type=WORK_PRODUCT", headers=_auth(token)
    )
    assert products.status_code == 200, products.text
    assert len(products.json()) == 22
    assert any("사업수행계획서" in t["label"] for t in products.json())

    metrics = client.get(f"/api/projects/{PID}/review-targets?type=METRIC", headers=_auth(token))
    assert [m["key"] for m in metrics.json()] == [
        "REPRESENTATIVE", "PROGRESS_WBS", "PROGRESS_ISSUE", "PROGRESS_WORK_PRODUCT"
    ]
    bad = client.get(f"/api/projects/{PID}/review-targets?type=NOPE", headers=_auth(token))
    assert bad.status_code == 400


@requires_db
def test_full_cycle_with_state_diff(client, client_token, issue_target):
    client_tok, contractor_tok = client_token("r2"), client_token("r3")
    body = {
        "targetType": "ISSUE",
        "targetKey": issue_target,
        "title": "이 이슈 처리 계획을 알려 주세요",
        "body": "마감 전에 닫혀야 합니다.",
    }

    # 용역사는 요청을 못 만든다
    denied = client.post(
        f"/api/projects/{PID}/review-requests", json=body, headers=_auth(contractor_tok)
    )
    assert denied.status_code == 403

    created = client.post(
        f"/api/projects/{PID}/review-requests", json=body, headers=_auth(client_tok)
    )
    assert created.status_code == 201, created.text
    req = created.json()
    assert req["status"] == "REQUESTED"
    assert req["targetLabel"] == "GH-8001 확인 요청 시험 이슈"
    rid = req["id"]

    # 미처리 건수가 사업 목록과 상세에 붙는다 (SWFR.WEB.006)
    detail = client.get(f"/api/projects/{PID}", headers=_auth(client_tok)).json()
    assert detail["openReviewRequestCount"] == 1
    listed = client.get("/api/projects?size=50", headers=_auth(client_tok)).json()
    assert next(p for p in listed["content"] if p["id"] == PID)["openReviewRequestCount"] == 1

    # 발주기관은 보고를 못 하고, 용역사는 요청 상태에서만 보고한다
    assert client.post(
        f"/api/review-requests/{rid}/report", json={"body": "x"}, headers=_auth(client_tok)
    ).status_code == 403

    # 그 사이 이슈가 닫혔다. 보고 시점에 시스템이 그 차이를 잡아낸다 (SWFR.WEB.005)
    with tx() as cur:
        cur.execute(
            "update issue set status = 'CLOSED', resolved_at = now() where id = %s",
            (issue_target,),
        )
    reported = client.post(
        f"/api/review-requests/{rid}/report",
        json={"body": "원인을 찾아 수정했고 이슈를 닫았습니다."},
        headers=_auth(contractor_tok),
    )
    assert reported.status_code == 200, reported.text
    rep = reported.json()
    assert rep["status"] == "REPORTED"
    assert rep["reportBody"].startswith("원인을")
    assert rep["snapshot"]["status"] == "OPEN"
    assert rep["currentState"]["status"] == "CLOSED"
    changed = {c["field"]: (c["before"], c["after"]) for c in rep["changes"]}
    assert changed["status"] == ("OPEN", "CLOSED")
    assert "resolved_at" in changed
    assert [e["kind"] for e in rep["events"]] == ["REQUESTED", "REPORTED"]

    # 용역사는 확인완료를 못 한다. 발주기관이 미흡하다고 다시 요청한다
    assert client.post(
        f"/api/review-requests/{rid}/confirm", headers=_auth(contractor_tok)
    ).status_code == 403
    again = client.post(
        f"/api/review-requests/{rid}/rerequest",
        json={"body": "재발 방지 조치도 적어 주세요."},
        headers=_auth(client_tok),
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "REQUESTED"
    assert again.json()["rerequestCount"] == 1
    assert again.json()["reportBody"] is None
    # 지난 보고는 이력에 남는다
    kinds = [e["kind"] for e in again.json()["events"]]
    assert kinds == ["REQUESTED", "REPORTED", "REREQUESTED"]
    assert again.json()["snapshot"]["status"] == "CLOSED"  # 재요청 시점 상태로 다시 뜬다

    client.post(
        f"/api/review-requests/{rid}/report",
        json={"body": "재발 방지: 회귀 시험을 추가했습니다."},
        headers=_auth(contractor_tok),
    )
    confirmed = client.post(f"/api/review-requests/{rid}/confirm", headers=_auth(client_tok))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["confirmedByName"]

    detail = client.get(f"/api/projects/{PID}", headers=_auth(client_tok)).json()
    assert detail["openReviewRequestCount"] == 0

    # 확인완료 후엔 다시 보고할 수 없다
    assert client.post(
        f"/api/review-requests/{rid}/report", json={"body": "x"}, headers=_auth(contractor_tok)
    ).status_code == 400


@requires_db
def test_request_on_missing_target_is_rejected(client, client_token):
    res = client.post(
        f"/api/projects/{PID}/review-requests",
        json={"targetType": "ISSUE", "targetKey": "00000000-0000-4000-8000-000000000000",
              "title": "없는 이슈", "body": ""},
        headers=_auth(client_token("r2")),
    )
    assert res.status_code == 400
