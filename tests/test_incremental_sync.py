"""증분 수집 (SWFR.CON.005) — 커서 승계와 반복 재현.

첫 수집은 BACKFILL, 이후는 POLL. 커서는 마지막 성공 잡의 cursor_to(=시작 시각)다.
"반복 수집이 재현 가능해야 한다"는 같은 원천에 세 번 돌려도 결과가 수렴한다는 뜻으로
검증한다 — 원천 무변경이면 잡 통계가 매회 같고, 원본 행이 늘지 않는다.
"""

from datetime import UTC, datetime

import httpx

from app.common import crypto
from app.db import tx
from app.integration import repository as integ_repo
from app.integration import sync
from app.integration.adapter import github_connector as gh
from app.integration.adapter import redmine_connector as rc
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


# ── 어댑터가 since 를 필터로 옮기는가 (MockTransport)


def _client_with(handler, monkeypatch, module):
    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(module.httpx, "Client", lambda **kw: real(transport=transport))


def test_레드마인은_updated_on_필터를_붙인다(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"issues": []})

    _client_with(handler, monkeypatch, rc)
    since = datetime(2026, 9, 9, 3, 0, 0, tzinfo=UTC)
    list(rc.fetch_items("http://x", "axlink", "k", "issue", 50, 5, since=since))
    assert seen["updated_on"] == ">=2026-09-09T03:00:00Z"


def test_깃허브_이슈는_since_커밋도_since_PR은_내림차순_경계(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/pulls"):
            return httpx.Response(
                200,
                json=[
                    {"number": 9, "updated_at": "2026-09-09T05:00:00Z"},
                    {
                        "number": 8,
                        "updated_at": "2026-09-01T00:00:00Z",
                    },  # 경계 이전 — 여기서 끊는다
                    {"number": 7, "updated_at": "2026-08-01T00:00:00Z"},
                ],
            )
        return httpx.Response(200, json=[])

    _client_with(handler, monkeypatch, gh)
    since = datetime(2026, 9, 9, 3, 0, 0, tzinfo=UTC)

    list(gh.fetch_items("https://api.github.com", "o/r", "t", "issue", 50, 2, since=since))
    list(gh.fetch_items("https://api.github.com", "o/r", "t", "commit", 50, 2, since=since))
    got = list(
        gh.fetch_items("https://api.github.com", "o/r", "t", "pull_request", 50, 2, since=since)
    )

    issue_params = calls[0][1]
    commit_params = calls[1][1]
    pr_params = calls[2][1]
    assert issue_params["since"] == "2026-09-09T03:00:00Z"
    assert commit_params["since"] == "2026-09-09T03:00:00Z"
    assert "since" not in pr_params and pr_params["direction"] == "desc"
    assert [item[0] for item in got] == ["pull_request:9"]  # 경계 이전 PR 은 나오지 않는다


def test_깃허브_마일스톤은_상태_불문_전량이고_since_를_안_붙인다(monkeypatch):
    """마일스톤에는 갱신 필터가 없다. 닫힌 것까지 받아야 달성 기록이 남는다(SWFR.PIP.007)."""
    seen = {}

    def handler(request):
        seen.update(path=request.url.path, params=dict(request.url.params))
        return httpx.Response(
            200,
            json=[
                {
                    "number": 3,
                    "title": "M2 연계·수집 기반 확보",
                    "state": "open",
                    "due_on": "2026-09-12T00:00:00Z",
                },
                {
                    "number": 1,
                    "title": "M0 착수보고",
                    "state": "closed",
                    "due_on": "2026-08-11T00:00:00Z",
                    "closed_at": "2026-08-11T09:00:00Z",
                },
            ],
        )

    _client_with(handler, monkeypatch, gh)
    since = datetime(2026, 9, 9, 3, 0, 0, tzinfo=UTC)
    got = list(
        gh.fetch_items("https://api.github.com", "o/r", "t", "milestone", 50, 2, since=since)
    )

    assert seen["path"].endswith("/repos/o/r/milestones")
    assert seen["params"]["state"] == "all" and "since" not in seen["params"]
    assert [item[0] for item in got] == ["milestone:3", "milestone:1"]
    assert got[1][1]["closed_at"] == "2026-08-11T09:00:00Z"  # 원본 그대로 보존된다


# ── 수집 흐름 — 커서 승계와 3회 재현 (시험 DB)


@requires_db
def test_첫_회는_전체_이후는_증분이고_반복해도_수렴한다(client, monkeypatch):
    source = {
        "1": {
            "id": 1,
            "subject": "이슈 하나",
            "description": "",
            "tracker": {"name": "작업"},
            "status": {"name": "신규", "is_closed": False},
            "updated_on": "2026-09-09T01:00:00Z",
        },
        "2": {
            "id": 2,
            "subject": "이슈 둘",
            "description": "",
            "tracker": {"name": "작업"},
            "status": {"name": "신규", "is_closed": False},
            "updated_on": "2026-09-09T01:00:00Z",
        },
    }
    received_since = []

    def fake_fetch(base, target, secret, kind, per_page, max_pages, since=None, until=None):
        received_since.append((kind, since))
        if kind != "issue":
            return
        for ext, payload in source.items():
            if since is not None and payload["updated_on"] <= since.strftime("%Y-%m-%dT%H:%M:%SZ"):
                continue  # 원천 도구의 updated_on 필터를 흉내낸다
            yield ext, payload

    monkeypatch.setattr(rc, "fetch_items", fake_fetch)
    monkeypatch.setattr(rc, "verify", lambda *a: None)

    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        conn = integ_repo.insert(
            cur,
            PID,
            org,
            "REDMINE",
            "레드마인",
            "http://localhost:3000",
            "axlink",
            crypto.encrypt("k"),
            "k***",
        )
        cid = str(conn["id"])
        try:

            def run():
                job_id = sync.run_sync(cur, conn)
                return integ_repo.find_sync_job(cur, job_id)

            first = run()
            assert first["kind"] == "BACKFILL" and first["status"] == "SUCCEEDED"
            assert first["stats_json"]["fetched"] == 2

            second, third = run(), run()
            # 커서가 승계된다 — 두 번째부터는 증분이고, 원천 무변경이면 아무것도 안 가져온다
            assert second["kind"] == "POLL" and third["kind"] == "POLL"
            assert received_since[0][1] is None
            assert received_since[3][1] is not None  # 2회차 issue 호출
            assert second["stats_json"]["fetched"] == 0
            # 「신규·갱신」은 바뀐 원본 수다. 첫 회 2, 변경 없는 회차 0 (AC-011-2, GH-213)
            assert first["stats_json"]["changed"] == 2
            assert second["stats_json"]["changed"] == 0
            # 3회 재현 — 통계가 같고 원본이 늘지 않는다
            assert second["stats_json"] == third["stats_json"]
            cur.execute(
                "select count(*) as c from raw_artifact where tool_connection_id = %s", (cid,)
            )
            assert cur.fetchone()["c"] == 2

            # 원천이 바뀌면 바뀐 것만 온다
            source["2"] = {
                **source["2"],
                "subject": "이슈 둘 (수정)",
                "updated_on": "2026-12-31T00:00:00Z",
            }
            fourth = run()
            assert fourth["kind"] == "POLL"
            assert fourth["stats_json"]["fetched"] == 1
            assert fourth["stats_json"]["skippedUnchanged"] == 0
        finally:
            cur.execute("delete from tool_connection where id = %s", (cid,))
