"""이슈·위험 화면. 도구에서 승격된 작업·결함을 사업 단위로 본다 (SWFR.WEB.001)."""

import pytest

from app.db import fetch_one, tx
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def two_issues():
    """열린 것 하나, 닫힌 것 하나. 수집 없이 표준 모델에 직접 넣고 끝나면 지운다."""
    with tx() as cur:
        open_id = fetch_one(
            cur,
            """
            insert into issue (project_id, issue_key, title, status, severity, assignee,
                               source_kind, source_updated_at)
            values (%s, 'GH-9001', '열린 시험 이슈', 'OPEN', 'MAJOR', 'park', 'MANUAL',
                    '2026-09-01T00:00:00Z')
            returning id
            """,
            (PID,),
        )["id"]
        closed_id = fetch_one(
            cur,
            """
            insert into issue (project_id, issue_key, title, status, severity, resolved_at,
                               source_kind, source_updated_at)
            values (%s, 'GH-9002', '닫힌 시험 이슈', 'CLOSED', 'MINOR',
                    '2026-09-10T00:00:00Z', 'MANUAL', '2026-09-10T00:00:00Z')
            returning id
            """,
            (PID,),
        )["id"]
    yield str(open_id), str(closed_id)
    with tx() as cur:
        cur.execute("delete from issue where id in (%s, %s)", (open_id, closed_id))


@requires_db
def test_lists_issues_open_first(client, client_token, two_issues):
    open_id, closed_id = two_issues
    res = client.get(f"/api/projects/{PID}/issues?size=100", headers=_auth(client_token("r2")))
    assert res.status_code == 200, res.text
    body = res.json()
    ids = [i["id"] for i in body["content"]]
    assert open_id in ids and closed_id in ids
    # 닫힌 것이 원천에서 더 최근에 움직였어도 열린 것이 먼저다
    assert ids.index(open_id) < ids.index(closed_id)

    opened = next(i for i in body["content"] if i["id"] == open_id)
    assert opened["key"] == "GH-9001"
    assert opened["status"] == "OPEN"
    assert opened["severity"] == "MAJOR"
    assert opened["assignee"] == "park"
    assert opened["resolvedAt"] is None
    assert opened["source"]["tool"] == "MANUAL"

    closed = next(i for i in body["content"] if i["id"] == closed_id)
    assert closed["resolvedAt"] is not None


@requires_db
def test_filters_by_status_and_text(client, client_token, two_issues):
    open_id, closed_id = two_issues
    token = client_token("r2")
    by_status = client.get(f"/api/projects/{PID}/issues?status=CLOSED", headers=_auth(token))
    ids = [i["id"] for i in by_status.json()["content"]]
    assert closed_id in ids and open_id not in ids

    by_text = client.get(f"/api/projects/{PID}/issues?q=GH-9001", headers=_auth(token))
    assert [i["id"] for i in by_text.json()["content"]] == [open_id]


@requires_db
def test_other_project_is_denied(client, client_token):
    other = "c0000000-0000-4000-8000-000000000099"
    res = client.get(f"/api/projects/{other}/issues", headers=_auth(client_token("r3")))
    assert res.status_code == 403
