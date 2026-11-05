"""일반 이슈의 원천 마일스톤 (GH-130, ARC-023, SWFR.CON.003).

GitHub 마일스톤은 수집만 되고 표준 모델에 없었다. 이제 마일스톤 표로 올리고 이슈가 그 행을
가리킨다. 이름·기한·상태는 원천 값 그대로다. 지정·미지정·닫힌 마일스톤 세 경우와, 다음 수집 때
기한 변경·지정 해제가 반영되는지 본다.
"""

import uuid
from datetime import UTC, datetime

from app.ai.embedding import embedding_port
from app.common import crypto
from app.db import tx
from app.integration import repository as integ_repo
from app.standard import mapping
from app.standard import service as standard
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _milestone(repo: str, number: int, title: str, due: str | None, closed: bool = False) -> dict:
    return {
        "number": number,
        "title": title,
        "state": "closed" if closed else "open",
        "due_on": f"{due}T07:00:00Z" if due else None,
        "closed_at": "2026-09-30T09:00:00Z" if closed else None,
        "updated_at": "2026-10-01T00:00:00Z",
        "html_url": f"https://github.com/{repo}/milestone/{number}",
    }


def _issue(repo: str, number: int, title: str, milestone: dict | None) -> dict:
    return {
        "number": number,
        "title": title,
        "body": "",
        "labels": [],
        "state": "open",
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-02T00:00:00Z",
        "html_url": f"https://github.com/{repo}/issues/{number}",
        "milestone": milestone,
    }


def _load(cur, cid: str, items: list[tuple[str, str, dict]]) -> None:
    job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
    for external_id, kind, payload in items:
        integ_repo.upsert_raw_artifact(cur, cid, external_id, kind, payload, job)
    now = datetime.now(UTC)
    integ_repo.finish_sync_job(cur, job, "SUCCEEDED", {}, now, now)


def _promote(cur, cid: str) -> None:
    cur.execute("select * from tool_connection where id = %s", (cid,))
    standard.promote_connection(cur, cur.fetchone(), embedding_port())


def _by_key(client, token: str, cid: str) -> dict[str, dict]:
    res = client.get(f"/api/projects/{PID}/issues?connectionId={cid}&size=50", headers=_auth(token))
    assert res.status_code == 200, res.text
    return {i["key"]: i for i in res.json()["content"]}


def test_마일스톤_원본을_행으로_옮긴다():
    rec = mapping.to_milestone(_milestone("o/r", 4, " M4 통합 PoC 완성 ", "2026-10-23"))
    assert rec["title"] == "M4 통합 PoC 완성" and rec["due_on"] == "2026-10-23"
    assert rec["state"] == "OPEN" and rec["number"] == 4
    assert mapping.to_milestone(_milestone("o/r", 1, "M0", None, closed=True))["state"] == "CLOSED"
    assert mapping.milestone_number(_issue("o/r", 1, "x", {"number": 4})) == 4
    assert mapping.milestone_number(_issue("o/r", 1, "x", None)) is None


@requires_db
def test_이슈에_원천_마일스톤의_이름_기한_상태가_보인다(client, client_token):
    token = client_token("r2")
    repo = f"x/ms-{uuid.uuid4().hex[:6]}"
    m4 = _milestone(repo, 4, "M4 통합 PoC 완성", "2026-10-23")
    m3 = _milestone(repo, 3, "M3 통합 현황 시연", "2026-09-30", closed=True)
    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        cid = str(
            integ_repo.insert(
                cur,
                PID,
                org,
                "GITHUB",
                "마일스톤 시험",
                "https://api.github.com",
                repo,
                crypto.encrypt("k"),
                "k***",
                {},
            )["id"]
        )
    try:
        with tx() as cur:
            _load(
                cur,
                cid,
                [
                    ("milestone:4", "milestone", m4),
                    ("milestone:3", "milestone", m3),
                    ("issue:1", "issue", _issue(repo, 1, "열린 마일스톤", {"number": 4})),
                    ("issue:2", "issue", _issue(repo, 2, "닫힌 마일스톤", {"number": 3})),
                    ("issue:3", "issue", _issue(repo, 3, "미지정", None)),
                ],
            )
            _promote(cur, cid)

        got = _by_key(client, token, cid)
        assert got["GH-1"]["milestone"] == {
            "title": "M4 통합 PoC 완성",
            "dueOn": "2026-10-23",
            "state": "OPEN",
            "url": f"https://github.com/{repo}/milestone/4",
        }
        assert got["GH-2"]["milestone"]["state"] == "CLOSED"
        assert got["GH-3"]["milestone"] is None

        # 다음 수집: 원천에서 M4 기한을 미루고, 1번 이슈의 마일스톤을 뺐다
        with tx() as cur:
            _load(
                cur,
                cid,
                [
                    ("milestone:4", "milestone", {**m4, "due_on": "2026-10-30T07:00:00Z"}),
                    ("issue:1", "issue", _issue(repo, 1, "열린 마일스톤", None)),
                    ("issue:3", "issue", _issue(repo, 3, "미지정", {"number": 4})),
                ],
            )
            _promote(cur, cid)
        got = _by_key(client, token, cid)
        assert got["GH-1"]["milestone"] is None
        assert got["GH-3"]["milestone"]["dueOn"] == "2026-10-30"
        assert got["GH-2"]["milestone"]["title"] == "M3 통합 현황 시연"
    finally:
        with tx() as cur:
            cur.execute("delete from issue where tool_connection_id = %s", (cid,))
            cur.execute("delete from milestone where tool_connection_id = %s", (cid,))
            cur.execute("delete from tool_connection where id = %s", (cid,))


def test_레드마인_버전_원본을_마일스톤_행으로_옮긴다():
    from app.standard import mapping_redmine

    rec = mapping_redmine.to_milestone(
        {
            "id": 11,
            "name": " 1차 ",
            "status": "closed",
            "due_date": "2026-04-30",
            "updated_on": "2026-04-28T09:00:00Z",
        },
        "https://redmine.example.test/",
    )
    assert rec["title"] == "1차" and rec["due_on"] == "2026-04-30" and rec["number"] == 11
    assert rec["state"] == "CLOSED" and rec["closed_at"] == "2026-04-28T09:00:00Z"
    assert rec["source_url"] == "https://redmine.example.test/versions/11"
    open_rec = mapping_redmine.to_milestone(
        {"id": 12, "name": "2차", "status": "open", "due_date": None, "updated_on": "x"}, "h"
    )
    assert open_rec["state"] == "OPEN" and open_rec["closed_at"] is None


@requires_db
def test_레드마인_이슈에_버전이_마일스톤으로_보인다(client, client_token):
    """Redmine 버전은 마일스톤 행이 되고 이슈의 fixed_version 이 그 행을 가리킨다(GH-214)."""
    token = client_token("r2")
    items = [
        (
            "version:11",
            "version",
            {
                "id": 11,
                "name": "1차",
                "status": "closed",
                "due_date": "2026-04-30",
                "updated_on": "2026-04-28T09:00:00Z",
            },
        ),
        (
            "version:14",
            "version",
            {
                "id": 14,
                "name": "상시",
                "status": "open",
                "due_date": None,
                "updated_on": "2026-09-01T00:00:00Z",
            },
        ),
        (
            "201",
            "issue",
            {
                "id": 201,
                "subject": "로그인 API 구현",
                "status": {"name": "종료", "is_closed": True},
                "priority": {"name": "보통"},
                "tracker": {"name": "일감"},
                "fixed_version": {"id": 11, "name": "1차"},
                "created_on": "2026-03-05T00:00:00Z",
                "updated_on": "2026-04-10T00:00:00Z",
            },
        ),
        (
            "206",
            "issue",
            {
                "id": 206,
                "subject": "코드 정리",
                "status": {"name": "신규", "is_closed": False},
                "priority": {"name": "낮음"},
                "tracker": {"name": "일감"},
                "created_on": "2026-03-05T00:00:00Z",
                "updated_on": "2026-04-10T00:00:00Z",
            },
        ),
    ]
    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        conn = integ_repo.insert(
            cur,
            PID,
            org,
            "REDMINE",
            "레드마인 버전",
            "https://redmine.example.test",
            f"ver-{uuid.uuid4().hex[:6]}",
            crypto.encrypt("k"),
            "k***",
        )
        cid = str(conn["id"])
    try:
        with tx() as cur:
            _load(cur, cid, items)
            _promote(cur, cid)
            rows = cur.execute(
                "select title, due_on, state, closed_at from milestone "
                "where tool_connection_id = %s order by number",
                (cid,),
            ).fetchall()
        assert [(r["title"], str(r["due_on"]), r["state"]) for r in rows] == [
            ("1차", "2026-04-30", "CLOSED"),
            ("상시", "None", "OPEN"),
        ]
        assert rows[0]["closed_at"] is not None
        by_key = _by_key(client, token, cid)
        assert by_key["RM-201"]["milestone"]["title"] == "1차"
        assert by_key["RM-201"]["milestone"]["dueOn"] == "2026-04-30"
        assert by_key["RM-206"]["milestone"] is None
    finally:
        with tx() as cur:
            cur.execute("delete from issue where tool_connection_id = %s", (cid,))
            cur.execute("delete from milestone where tool_connection_id = %s", (cid,))
            cur.execute("delete from raw_artifact where tool_connection_id = %s", (cid,))
            cur.execute("delete from sync_job where tool_connection_id = %s", (cid,))
            cur.execute("delete from tool_connection where id = %s", (cid,))
