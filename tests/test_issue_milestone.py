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
        "number": number, "title": title, "state": "closed" if closed else "open",
        "due_on": f"{due}T07:00:00Z" if due else None,
        "closed_at": "2026-09-30T09:00:00Z" if closed else None,
        "updated_at": "2026-10-01T00:00:00Z",
        "html_url": f"https://github.com/{repo}/milestone/{number}",
    }


def _issue(repo: str, number: int, title: str, milestone: dict | None) -> dict:
    return {
        "number": number, "title": title, "body": "", "labels": [], "state": "open",
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z",
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
    res = client.get(
        f"/api/projects/{PID}/issues?connectionId={cid}&size=50", headers=_auth(token)
    )
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
        cid = str(integ_repo.insert(
            cur, PID, org, "GITHUB", "마일스톤 시험", "https://api.github.com", repo,
            crypto.encrypt("k"), "k***", {},
        )["id"])
    try:
        with tx() as cur:
            _load(cur, cid, [
                ("milestone:4", "milestone", m4),
                ("milestone:3", "milestone", m3),
                ("issue:1", "issue", _issue(repo, 1, "열린 마일스톤", {"number": 4})),
                ("issue:2", "issue", _issue(repo, 2, "닫힌 마일스톤", {"number": 3})),
                ("issue:3", "issue", _issue(repo, 3, "미지정", None)),
            ])
            _promote(cur, cid)

        got = _by_key(client, token, cid)
        assert got["GH-1"]["milestone"] == {
            "title": "M4 통합 PoC 완성", "dueOn": "2026-10-23", "state": "OPEN",
            "url": f"https://github.com/{repo}/milestone/4",
        }
        assert got["GH-2"]["milestone"]["state"] == "CLOSED"
        assert got["GH-3"]["milestone"] is None

        # 다음 수집: 원천에서 M4 기한을 미루고, 1번 이슈의 마일스톤을 뺐다
        with tx() as cur:
            _load(cur, cid, [
                ("milestone:4", "milestone", {**m4, "due_on": "2026-10-30T07:00:00Z"}),
                ("issue:1", "issue", _issue(repo, 1, "열린 마일스톤", None)),
                ("issue:3", "issue", _issue(repo, 3, "미지정", {"number": 4})),
            ])
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
