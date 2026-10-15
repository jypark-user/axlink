"""Redmine 수집 결함 세 건 (SWFR.CON.004 · SWFR.CON.005 · SWFR.CON.006).

1. 일감·버전·트래커 번호가 같으면 원본이 서로 덮어썼다(10-13 실서버 시험: 일감 10건 중 2건만 남음).
2. 키가 무효거나 프로젝트 권한이 빠져도 "권한 없어 건너뛴 항목" 메모만 남고 성공으로 끝났다.
3. 화면의 "전체 수집"이 kind=BACKFILL 을 보내도 서버가 무시해 증분만 돌았다.
"""

import httpx

from app.common import crypto, errors
from app.db import tx
from app.integration import repository as integ_repo
from app.integration import sync
from app.integration.adapter import redmine_connector as rc
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"
_REAL_CLIENT = httpx.Client  # 여러 번 바꿔 끼워도 진짜 Client 를 감싼다


def _issue(i: int) -> dict:
    return {"id": i, "subject": f"일감 {i}", "description": "",
            "tracker": {"id": 1, "name": "작업"}, "status": {"name": "신규", "is_closed": False},
            "priority": {"name": "보통"}, "updated_on": "2026-10-13T01:00:00Z"}


def _source(kind: str) -> list[dict]:
    if kind == "issue":
        return [_issue(1), _issue(2), _issue(7)]
    if kind == "version":
        return [{"id": 7, "name": "M2"}, {"id": 2, "name": "M1"}]
    return [{"id": 1, "name": "작업"}, {"id": 2, "name": "결함"}]


def _transport(status_of: dict[str, int]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        kind = "issue" if path.endswith("/issues.json") else (
            "version" if path.endswith("/versions.json") else "tracker")
        code = status_of.get(kind, 200)
        if code != 200:
            return httpx.Response(code, json={})
        return httpx.Response(200, json={f"{kind}s": _source(kind)})
    return httpx.MockTransport(handler)


def _patch(monkeypatch, status_of: dict[str, int]) -> None:
    transport = _transport(status_of)
    monkeypatch.setattr(rc.httpx, "Client", lambda **kw: _REAL_CLIENT(transport=transport))


def test_버전_트래커는_종류를_붙여_일감_번호와_겹치지_않는다(monkeypatch):
    _patch(monkeypatch, {})
    got = {kind: [e for e, _ in rc.fetch_items("http://x", "p", "k", kind, 50, 2)]
           for kind in rc.ITEM_KINDS}
    assert got["issue"] == ["1", "2", "7"]  # 일감은 번호 그대로(RM-번호 해석이 쓴다)
    assert got["version"] == ["version:7", "version:2"]
    assert got["tracker"] == ["tracker:1", "tracker:2"]
    assert rc.external_id("issue", {"id": 3}) == "3"


def test_필수_항목이나_모든_항목이_막히면_실패로_본다():
    class Conn:
        item_kinds = ("issue", "version", "tracker")
        required_kinds = ("issue",)

    sync._fail_if_core_denied(Conn, [])  # 막힌 것이 없으면 그대로
    sync._fail_if_core_denied(Conn, ["version"])  # 필수 아닌 일부만 막히면 부분 성공
    for denied in (["issue"], ["issue", "version"]):
        try:
            sync._fail_if_core_denied(Conn, denied)
        except errors.ApiError as exc:
            assert exc.code == "TOOL_AUTH" and "issue" in exc.message
        else:
            raise AssertionError(denied)

    class AllOptional:
        item_kinds = ("a", "b")

    sync._fail_if_core_denied(AllOptional, ["a"])
    try:
        sync._fail_if_core_denied(AllOptional, ["a", "b"])
    except errors.ApiError:
        pass
    else:
        raise AssertionError("모든 항목이 막혔는데 통과했다")


def _connection(cur) -> dict:
    cur.execute("select organization_id from app_user where username = 'r3'")
    org = str(cur.fetchone()["organization_id"])
    return integ_repo.insert(
        cur, PID, org, "REDMINE", "레드마인 결함 시험", "http://localhost:3000",
        "defects", crypto.encrypt("k"), "k***",
    )


@requires_db
def test_실제_수집에서_일감이_버전_트래커에_덮이지_않는다(client, monkeypatch):
    _patch(monkeypatch, {})
    with tx() as cur:
        conn = _connection(cur)
        cid = str(conn["id"])
        try:
            job = integ_repo.find_sync_job(cur, sync.run_sync(cur, conn))
            assert job["status"] == "SUCCEEDED", job
            cur.execute(
                "select object_kind, count(*) as n from raw_artifact "
                "where tool_connection_id = %s group by 1", (cid,))
            assert {r["object_kind"]: r["n"] for r in cur.fetchall()} == {
                "issue": 3, "version": 2, "tracker": 2}
            cur.execute("select count(*) as n from issue where tool_connection_id = %s", (cid,))
            assert cur.fetchone()["n"] == 3
        finally:
            cur.execute("delete from tool_connection where id = %s", (cid,))


@requires_db
def test_키가_무효면_수집은_실패하고_받아_둔_데이터는_남는다(client, monkeypatch):
    with tx() as cur:
        conn = _connection(cur)
        cid = str(conn["id"])
        try:
            _patch(monkeypatch, {})
            ok = integ_repo.find_sync_job(cur, sync.run_sync(cur, conn))
            assert ok["status"] == "SUCCEEDED"

            # 키 무효: 일감·버전은 401, 트래커는 익명으로도 보이는 Redmine 동작을 흉내낸다
            _patch(monkeypatch, {"issue": 401, "version": 401})
            bad = integ_repo.find_sync_job(cur, sync.run_sync(cur, conn))
            assert bad["status"] == "FAILED", (bad["error"], bad["stats_json"])
            assert bad["error_code"] == "TOOL_AUTH_FAILED"
            assert "issue" in bad["error"]

            # 프로젝트 권한 없음(403)도 같다
            _patch(monkeypatch, {"issue": 403, "version": 403})
            denied = integ_repo.find_sync_job(cur, sync.run_sync(cur, conn))
            assert denied["status"] == "FAILED"

            cur.execute("select count(*) as n from issue where tool_connection_id = %s", (cid,))
            assert cur.fetchone()["n"] == 3  # 실패가 앞서 받은 데이터를 지우지 않는다

            # 필수 아닌 항목만 막히면 지금처럼 부분 성공이다
            _patch(monkeypatch, {"version": 403})
            partial = integ_repo.find_sync_job(cur, sync.run_sync(cur, conn, full=True))
            assert partial["status"] == "SUCCEEDED"
            assert "version" in (partial["error"] or "")
        finally:
            cur.execute("delete from tool_connection where id = %s", (cid,))


@requires_db
def test_전체_수집을_요청하면_커서를_무시하고_처음부터_읽는다(client, client_token, monkeypatch):
    seen = []

    def fake_fetch(base, target, secret, kind, per_page, max_pages, since=None):
        seen.append((kind, since))
        if kind == "issue":
            yield "1", _issue(1)

    monkeypatch.setattr(rc, "fetch_items", fake_fetch)
    with tx() as cur:
        conn = _connection(cur)
        cid = str(conn["id"])
        cur.execute("update tool_connection set status = 'ACTIVE' where id = %s", (cid,))
    try:
        auth = {"Authorization": f"Bearer {client_token('r3')}"}
        first = client.post(f"/api/connections/{cid}/sync", headers=auth)
        assert first.status_code == 202, first.text
        poll = client.post(f"/api/connections/{cid}/sync", json={"kind": "POLL"}, headers=auth)
        assert poll.json()["kind"] == "POLL"
        full = client.post(f"/api/connections/{cid}/sync", json={"kind": "BACKFILL"},
                           headers=auth)
        assert full.status_code == 202, full.text
        assert full.json()["kind"] == "BACKFILL"
        issue_calls = [s for k, s in seen if k == "issue"]
        assert issue_calls[0] is None and issue_calls[1] is not None and issue_calls[2] is None
    finally:
        with tx() as cur:
            cur.execute("delete from tool_connection where id = %s", (cid,))
