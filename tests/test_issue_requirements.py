"""이슈 목록의 관련 요구사항 (2026-11-18 사용자 지시).

이슈 제목에 요구사항 코드가 붙어 있으면 그 요구사항에 붙은 이슈로 본다. 이슈 목록은 요구사항
화면과 같은 추적 연결을 보이고, 연결이 없는 이슈는 빈 목록이다(화면은 「-」).
"""

import uuid
from datetime import UTC, datetime

from app.ai.embedding import embedding_port
from app.common import crypto
from app.db import tx
from app.integration import repository as integ_repo
from app.standard import service as standard
from app.standard import trace_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _issue(repo: str, number: int, title: str) -> dict:
    return {
        "number": number, "title": title, "body": "", "labels": [], "state": "open",
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z",
        "html_url": f"https://github.com/{repo}/issues/{number}",
    }


@requires_db
def test_제목에_요구사항_코드가_있는_이슈는_그_요구사항이_보인다(client, client_token):
    token = client_token("r2")
    repo = f"x/rq-{uuid.uuid4().hex[:6]}"
    code = f"SWFR.TST.{uuid.uuid4().int % 900 + 100}"
    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        cur.execute(
            "insert into requirement (project_id, code, title) values (%s, %s, %s) returning id",
            (PID, code, "TST 이슈 연결 요구사항"),
        )
        rid = str(cur.fetchone()["id"])
        cid = str(integ_repo.insert(
            cur, PID, org, "GITHUB", "요구사항 연결 시험", "https://api.github.com", repo,
            crypto.encrypt("k"), "k***", {},
        )["id"])
    try:
        with tx() as cur:
            job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
            for n, title in ((1, f"[{code}] 화면 구현"), (2, "요구사항 표시 없는 작업")):
                integ_repo.upsert_raw_artifact(cur, cid, f"issue:{n}", "issue",
                                               _issue(repo, n, title), job)
            now = datetime.now(UTC)
            integ_repo.finish_sync_job(cur, job, "SUCCEEDED", {}, now, now)
            cur.execute("select * from tool_connection where id = %s", (cid,))
            standard.promote_connection(cur, cur.fetchone(), embedding_port())
            trace_service.build_project_links(cur, PID)

        res = client.get(f"/api/projects/{PID}/issues?connectionId={cid}&size=50",
                         headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200, res.text
        got = {i["key"]: i["requirements"] for i in res.json()["content"]}
        assert got["GH-1"] == [{"id": rid, "code": code, "title": "TST 이슈 연결 요구사항"}]
        assert got["GH-2"] == []
    finally:
        with tx() as cur:
            cur.execute("delete from trace_link where to_id = %s or from_id in "
                        "(select id from issue where tool_connection_id = %s)", (rid, cid))
            cur.execute("delete from issue where tool_connection_id = %s", (cid,))
            cur.execute("delete from tool_connection where id = %s", (cid,))
            cur.execute("delete from requirement where id = %s", (rid,))
