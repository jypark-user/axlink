"""일반 이슈 화면. 도구에서 승격된 작업·결함을 사업 단위로 본다 (SWFR.WEB.001)."""

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


# ---------------------------------------------------------------- 카드 집계


def _summary(client, token: str) -> dict[str, int]:
    res = client.get(f"/api/projects/{PID}/issues/summary", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()


def _all_rows(client, token: str, size: int) -> list[dict]:
    """목록을 끝까지 넘겨 모은다. 화면의 fetchAllPages 와 같은 방식이다."""
    rows: list[dict] = []
    page = 0
    while True:
        body = client.get(
            f"/api/projects/{PID}/issues?page={page}&size={size}", headers=_auth(token)
        ).json()
        rows += body["content"]
        if not body["hasNext"]:
            assert len(rows) == body["totalElements"]
            return rows
        page += 1


# 130건. 상태 넷·심각도 다섯·담당(있음/없음/공백)을 돌려 가며 섞는다
MANY = 130
_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED")
_SEVERITIES = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "TRIVIAL")
_ASSIGNEES = ("kim", None, " ")


def _many_expected() -> dict[str, int]:
    exp = {"total": MANY, "open": 0, "closed": 0, "heavyOpen": 0, "unassignedOpen": 0,
           "unspecifiedOpen": 0}
    for n in range(MANY):
        status, sev, who = _STATUSES[n % 4], _SEVERITIES[n % 5], _ASSIGNEES[n % 3]
        if status in ("OPEN", "IN_PROGRESS"):
            exp["open"] += 1
            exp["heavyOpen"] += sev in ("BLOCKER", "CRITICAL", "MAJOR")
            exp["unassignedOpen"] += who is None or not who.strip()
        else:
            exp["closed"] += 1
    return exp


@pytest.fixture
def many_issues():
    with tx() as cur:
        for n in range(MANY):
            status = _STATUSES[n % 4]
            cur.execute(
                """
                insert into issue (project_id, issue_key, title, status, severity, assignee,
                                   resolved_at, source_kind)
                values (%s, %s, %s, %s, %s, %s, %s, 'MANUAL')
                """,
                (
                    PID, f"GH-77{n:03d}", f"대량 시험 이슈 {n}", status, _SEVERITIES[n % 5],
                    _ASSIGNEES[n % 3],
                    "2026-09-10T00:00:00Z" if status in ("RESOLVED", "CLOSED") else None,
                ),
            )
    yield
    with tx() as cur:
        cur.execute("delete from issue where issue_key like 'GH-77%%' and project_id = %s", (PID,))


@requires_db
def test_카드는_100건을_넘어도_사업_전체를_센다(client, client_token, many_issues):
    token = client_token("r2")
    got = _summary(client, token)
    rows = _all_rows(client, token, 200)

    # 기대값은 넣은 130건으로 따로 계산하고, 원래 있던 행은 목록에서 같은 규칙으로 센다
    before = [r for r in rows if not r["key"].startswith("GH-77")]
    exp = _many_expected()
    opened = [r for r in before if r["status"] in ("OPEN", "IN_PROGRESS")]
    exp["total"] += len(before)
    exp["open"] += len(opened)
    exp["closed"] += len(before) - len(opened)
    exp["heavyOpen"] += sum(r["severity"] in ("BLOCKER", "CRITICAL", "MAJOR") for r in opened)
    exp["unassignedOpen"] += sum(not (r["assignee"] or "").strip() for r in opened)
    exp["unspecifiedOpen"] += sum(r["severity"] is None for r in opened)

    assert got == exp
    assert got["total"] > 100
    assert got["open"] + got["closed"] == got["total"]


@requires_db
def test_카드는_목록의_쪽_크기와_상관없다(client, client_token, many_issues):
    token = client_token("r2")
    got = _summary(client, token)
    first = client.get(f"/api/projects/{PID}/issues?size=20", headers=_auth(token)).json()
    assert len(first["content"]) == 20
    assert got["total"] == first["totalElements"]
    # 상태 필터 건수와도 맞는다. 목록과 카드가 같은 테이블·같은 사업 조건이다
    open_n = sum(
        client.get(f"/api/projects/{PID}/issues?status={s}&size=1", headers=_auth(token))
        .json()["totalElements"]
        for s in ("OPEN", "IN_PROGRESS")
    )
    assert got["open"] == open_n


@requires_db
def test_목록은_쪽을_넘기면_모든_행에_닿는다(client, client_token, many_issues):
    token = client_token("r2")
    for size in (50, 200):
        rows = _all_rows(client, token, size)
        keys = [r["key"] for r in rows]
        assert len(keys) == len(set(r["id"] for r in rows))
        assert {f"GH-77{n:03d}" for n in range(MANY)} <= set(keys)


@requires_db
def test_카드도_목록과_같은_권한을_쓴다(client, client_token):
    other = "c0000000-0000-4000-8000-000000000099"
    token = client_token("r3")
    assert client.get(f"/api/projects/{other}/issues", headers=_auth(token)).status_code == 403
    res = client.get(f"/api/projects/{other}/issues/summary", headers=_auth(token))
    assert res.status_code == 403
    assert client.get(f"/api/projects/{PID}/issues/summary").status_code == 401
