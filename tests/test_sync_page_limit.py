"""회차 상한을 넘는 수집 (SWFR.CON.005, 점검 DATA-01).

한 회차는 항목종류마다 50건 × 20쪽(1,000건)까지만 읽는다. 상한에 걸렸는데도 성공 커서를
지금 시각으로 넘기면, 못 읽은 항목은 다시 갱신되기 전까지 영영 들어오지 않는다.
상한에 걸린 종류는 다음 회차가 이어 읽어야 한다.

GitHub·Redmine 응답은 MockTransport 로 흉내 낸다. 실제 도구처럼 since·until·정렬·쪽 번호를
따른다. 수집 결과는 시험 DB 의 원본(raw_artifact) 건수로 본다.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.common import crypto
from app.db import fetch_all, fetch_one, tx
from app.integration import repository as integ_repo
from app.integration import sync
from app.integration.adapter import github_connector as gh
from app.integration.adapter import redmine_connector as rc
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
_REAL_CLIENT = httpx.Client
_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _z(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _gh_issue(n: int, updated: datetime) -> dict:
    return {"number": n, "title": f"이슈 {n}", "body": "", "labels": [], "state": "open",
            "created_at": _z(_BASE), "updated_at": _z(updated),
            "html_url": f"https://github.com/o/r/issues/{n}"}


def _gh_commit(n: int, at: datetime) -> dict:
    sha = f"{n:040x}"
    return {"sha": sha, "html_url": f"https://github.com/o/r/commit/{sha}",
            "commit": {"message": f"chore: {n}  [chore]",
                       "author": {"name": "x", "date": _z(at)},
                       "committer": {"name": "x", "date": _z(at)}}}


class GitHubSource:
    """since·until·정렬·쪽 번호를 지키는 가짜 GitHub. fail_after 쪽 뒤로는 500 을 낸다."""

    def __init__(self, issues: list[dict], commits: list[dict]) -> None:
        self.issues, self.commits = issues, commits
        self.fail = False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if self.fail:
            return httpx.Response(500, json={})
        path, q = req.url.path, req.url.params
        page, per = int(q.get("page", 1)), int(q.get("per_page", 30))
        if path.endswith("/issues"):
            items = [i for i in self.issues if i["updated_at"] >= q.get("since", "")]
            items.sort(key=lambda i: (i["updated_at"], i["number"]))
        elif path.endswith("/commits"):
            def at(c: dict) -> str:
                return c["commit"]["committer"]["date"]
            items = [c for c in self.commits
                     if at(c) >= q.get("since", "") and at(c) <= q.get("until", "9999")]
            items.sort(key=lambda c: (at(c), c["sha"]), reverse=True)  # 최신부터
        elif path.endswith(("/pulls", "/milestones")):
            items = []
        else:
            return httpx.Response(404, json={})
        return httpx.Response(200, json=items[(page - 1) * per: page * per])


class RedmineSource:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = issues

    def __call__(self, req: httpx.Request) -> httpx.Response:
        q = req.url.params
        if not req.url.path.endswith("/issues.json"):
            key = "versions" if req.url.path.endswith("/versions.json") else "trackers"
            return httpx.Response(200, json={key: []})
        since = q.get("updated_on", ">=").removeprefix(">=")
        items = [i for i in self.issues if i["updated_on"] >= since]
        items.sort(key=lambda i: (i["updated_on"], i["id"]))
        offset, limit = int(q.get("offset", 0)), int(q.get("limit", 25))
        return httpx.Response(200, json={"issues": items[offset: offset + limit]})


def _rm_issue(n: int, updated: datetime) -> dict:
    return {"id": n, "subject": f"일감 {n}", "description": "",
            "tracker": {"id": 1, "name": "작업"}, "status": {"name": "신규", "is_closed": False},
            "priority": {"name": "보통"}, "created_on": _z(_BASE), "updated_on": _z(updated)}


@pytest.fixture
def conn(monkeypatch):
    made: list[str] = []

    def connect(tool: str, handler) -> dict:
        module = gh if tool == "GITHUB" else rc
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(module.httpx, "Client", lambda **kw: _REAL_CLIENT(transport=transport))
        base = "https://api.github.com" if tool == "GITHUB" else "https://redmine.invalid"
        with tx() as cur:
            org = str(fetch_one(cur, "select organization_id from app_user "
                                     "where username = 'r3'")["organization_id"])
            row = integ_repo.insert(cur, PID, org, tool, f"상한 시험 {tool}", base,
                                    f"o/limit-{uuid.uuid4().hex[:6]}", crypto.encrypt("k"),
                                    "k***", {})
        made.append(str(row["id"]))
        return row

    yield connect
    with tx() as cur:
        for cid in made:
            for table in ("issue", "code_change", "requirement", "risk"):
                cur.execute(f"delete from {table} where tool_connection_id = %s", (cid,))
            cur.execute("delete from raw_artifact where tool_connection_id = %s", (cid,))
            cur.execute("delete from sync_job where tool_connection_id = %s", (cid,))
            cur.execute("delete from tool_connection where id = %s", (cid,))


def _run(connection: dict) -> dict:
    with tx() as cur:
        job_id = sync.run_sync(cur, connection)
        return fetch_one(cur, "select status, error, stats_json from sync_job where id = %s",
                         (job_id,))


def _raw(connection: dict, kind: str) -> set[str]:
    with tx() as cur:
        rows = fetch_all(cur, "select external_id from raw_artifact "
                              "where tool_connection_id = %s and object_kind = %s",
                         (str(connection["id"]), kind))
    return {r["external_id"] for r in rows}


@requires_db
def test_깃허브_이슈가_상한을_넘으면_다음_회차에_나머지를_읽는다(conn):
    issues = [_gh_issue(n, _BASE + timedelta(minutes=n)) for n in range(1, 1002)]
    c = conn("GITHUB", GitHubSource(issues, []))

    first = _run(c)
    assert first["status"] == "SUCCEEDED"
    assert len(_raw(c, "issue")) == 1000
    assert "상한" in (first["error"] or "")  # 다 읽지 못했다는 사실을 남긴다

    second = _run(c)
    assert second["status"] == "SUCCEEDED"
    assert _raw(c, "issue") == {f"issue:{n}" for n in range(1, 1002)}
    assert "상한" not in (second["error"] or "")

    _run(c)  # 도구 쪽이 그대로면 더 늘지 않는다
    assert len(_raw(c, "issue")) == 1001


@requires_db
def test_같은_갱신_시각이_상한_경계에_걸려도_빠지지_않는다(conn):
    same = _BASE + timedelta(days=1)
    issues = [_gh_issue(n, _BASE + timedelta(minutes=n)) for n in range(1, 996)]
    issues += [_gh_issue(n, same) for n in range(996, 1011)]  # 1,000번째 앞뒤가 같은 시각
    c = conn("GITHUB", GitHubSource(issues, []))
    _run(c)
    _run(c)
    assert len(_raw(c, "issue")) == 1010


@requires_db
def test_커밋은_최신부터_오므로_못_읽은_오래된_구간을_다음_회차에_읽는다(conn):
    commits = [_gh_commit(n, _BASE + timedelta(minutes=n)) for n in range(1, 1002)]
    c = conn("GITHUB", GitHubSource([], commits))
    _run(c)
    assert len(_raw(c, "commit")) == 1000  # 최신 1,000건. 가장 오래된 1건이 남았다
    _run(c)
    assert len(_raw(c, "commit")) == 1001


@requires_db
def test_레드마인_일감이_상한을_넘으면_다음_회차에_나머지를_읽는다(conn):
    issues = [_rm_issue(n, _BASE + timedelta(minutes=n)) for n in range(1, 1002)]
    c = conn("REDMINE", RedmineSource(issues))
    first = _run(c)
    assert first["status"] == "SUCCEEDED" and len(_raw(c, "issue")) == 1000
    _run(c)
    assert _raw(c, "issue") == {str(n) for n in range(1, 1002)}


@requires_db
def test_이어_읽던_회차가_실패하면_다음_성공_회차가_이어_읽는다(conn):
    issues = [_gh_issue(n, _BASE + timedelta(minutes=n)) for n in range(1, 1002)]
    source = GitHubSource(issues, [])
    c = conn("GITHUB", source)
    _run(c)
    source.fail = True
    assert _run(c)["status"] == "FAILED"
    source.fail = False
    _run(c)
    assert len(_raw(c, "issue")) == 1001
