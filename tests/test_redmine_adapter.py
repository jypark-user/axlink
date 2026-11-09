"""Redmine 어댑터 (SWFR.CON.004) — 매핑·페이지·승격.

실제 Redmine 을 때리지 않는다. HTTP 는 MockTransport 로, 승격은 시험 DB 로 검증한다.
실연결 확인은 연동 테스트 단계에서 따로 한다.
"""

from datetime import UTC, datetime

import httpx

from app.common import crypto
from app.db import tx
from app.integration import repository as integ_repo
from app.integration.adapter import redmine_connector as rc
from app.standard import mapping_redmine
from app.standard import service as standard
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"


def _issue(id=1, tracker="작업", status="신규", closed=False, priority="보통", **over):
    payload = {
        "id": id,
        "subject": f"이슈 {id}",
        "description": "본문",
        "tracker": {"id": 2, "name": tracker},
        "status": {"id": 1, "name": status, "is_closed": closed},
        "priority": {"id": 2, "name": priority},
        "assigned_to": {"id": 1, "name": "박PM"},
        "custom_fields": [{"id": 1, "name": "REQ ID", "value": "SWFR.CON.004"}],
        "created_on": "2026-09-09T02:58:03Z",
        "updated_on": "2026-09-09T03:00:00Z",
        "closed_on": "2026-09-09T04:00:00Z" if closed else None,
    }
    payload.update(over)
    return payload


# ── 매핑 (순수 함수)

def test_작업_이슈는_issue_로_간다():
    rec = mapping_redmine.to_issue(_issue(status="진행"), "http://localhost:3000")
    assert rec["issue_key"] == "RM-1"
    assert rec["status"] == "IN_PROGRESS"
    assert rec["assignee"] == "박PM"
    assert rec["external_url"] == "http://localhost:3000/issues/1"
    assert rec["resolved_at"] is None


def test_닫힌_이슈는_상태_이름과_무관하게_CLOSED():
    """상태 이름은 인스턴스마다 다르다. is_closed 플래그가 1차 근거다."""
    rec = mapping_redmine.to_issue(_issue(status="아무거나", closed=True), "http://x")
    assert rec["status"] == "CLOSED"
    assert rec["resolved_at"] == "2026-09-09T04:00:00Z"


def test_리스크_트래커_판별과_승격_모양():
    payload = _issue(tracker="리스크", priority="높음")
    assert mapping_redmine.is_risk(payload)
    rec = mapping_redmine.to_risk(payload, "http://x")
    assert rec["severity"] == "HIGH"
    assert rec["status"] == "OPEN"
    assert rec["identified_at"] == "2026-09-09"


def test_REQ_ID_커스텀_필드를_읽는다():
    assert mapping_redmine.req_id(_issue()) == "SWFR.CON.004"
    assert mapping_redmine.req_id(_issue(custom_fields=[])) is None


# ── 커넥터 (MockTransport)

def _client_with(handler, monkeypatch):
    # rc.httpx 는 이 파일의 httpx 와 같은 모듈 객체다 — 원본 클래스를 잡아둬야 재귀가 안 된다.
    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(rc.httpx, "Client", lambda **kw: real(transport=transport))


def test_이슈를_offset_페이지로_끝까지_가져온다(monkeypatch):
    def handler(request):
        offset = int(request.url.params.get("offset", 0))
        assert request.headers["X-Redmine-API-Key"] == "k"
        assert request.url.params["status_id"] == "*"
        batch = [_issue(id=offset + n) for n in range(2 if offset == 0 else 1)]
        return httpx.Response(200, json={"issues": batch, "total_count": 3})

    _client_with(handler, monkeypatch)
    items = list(rc.fetch_items("http://x", "axlink", "k", "issue", per_page=2, max_pages=5))
    assert [i[0] for i in items] == ["0", "1", "2"]


def test_verify_는_권한_빠진_항목을_denied_로_돌려준다(monkeypatch):
    def handler(request):
        path = request.url.path
        if path == "/projects/axlink.json":
            return httpx.Response(200, json={"project": {"name": "AX Link"}})
        if path == "/issues.json":
            return httpx.Response(403)
        return httpx.Response(200, json={"versions": [], "trackers": []})

    _client_with(handler, monkeypatch)
    probe = rc.verify("http://x", "axlink", "k")
    assert probe.name == "AX Link"
    assert probe.denied == ["issue"]
    assert set(probe.readable) == {"version", "tracker"}


def test_파일_수집은_없다():
    assert rc.fetch_file("http://x", "axlink", "k", "docs/WBS.xlsx") is None


# ── 승격 (시험 DB)

@requires_db
def test_레드마인_원본이_표준_모델로_오른다(client):
    from app.ai.embedding import embedding_port

    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])  # 용역사 조직 — 연결은 용역사가 붙인다
        conn = integ_repo.insert(
            cur, PID, org, "REDMINE", "레드마인", "http://localhost:3000",
            "axlink", crypto.encrypt("k"), "k***",
        )
        cid = str(conn["id"])
        try:
            job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
            integ_repo.upsert_raw_artifact(cur, cid, "1", "issue", _issue(id=1, status="진행"), job)
            integ_repo.upsert_raw_artifact(
                cur, cid, "6", "issue", _issue(id=6, tracker="리스크", priority="높음"), job
            )
            integ_repo.upsert_raw_artifact(cur, cid, "2", "version", {"id": 2, "name": "M2"}, job)

            result = standard.promote_connection(cur, conn, embedding_port())

            # 버전은 마일스톤으로 올라간다(GH-214). 원본 보존만 하는 것은 트래커뿐이다
            assert result.by_type == {"ISSUE": 1, "RISK": 1, "MILESTONE": 1}
            assert result.raw_only == 0
            assert result.unmapped == 0

            cur.execute("select issue_key, status from issue where tool_connection_id = %s", (cid,))
            row = cur.fetchone()
            assert row["issue_key"] == "RM-1" and row["status"] == "IN_PROGRESS"
            cur.execute("select severity from risk where tool_connection_id = %s", (cid,))
            assert cur.fetchone()["severity"] == "HIGH"
        finally:
            cur.execute("delete from tool_connection where id = %s", (cid,))


@requires_db
def test_이슈_응답에_트래커_요구사항_ID_이슈관계가_보인다(client, client_token):
    """원시본의 트래커·커스텀 필드·이슈관계가 API 응답에 보인다(AC-043-2, GH-224)."""
    from app.ai.embedding import embedding_port

    token = client_token("r2")
    with tx() as cur:
        cur.execute("select organization_id from app_user where username = 'r3'")
        org = str(cur.fetchone()["organization_id"])
        conn = integ_repo.insert(
            cur, PID, org, "REDMINE", "레드마인 필드", "http://localhost:3000",
            f"fields-{datetime.now(UTC).timestamp()}", crypto.encrypt("k"), "k***",
        )
        cid = str(conn["id"])
    relation = {"id": 9, "issue_id": 204, "issue_to_id": 203, "relation_type": "precedes"}
    try:
        with tx() as cur:
            job = integ_repo.insert_sync_job(cur, cid, "BACKFILL", None, datetime.now(UTC))
            integ_repo.upsert_raw_artifact(cur, cid, "203", "issue", _issue(
                id=203, tracker="일감", status="종료", closed=True, priority="높음",
                custom_fields=[{"id": 1, "name": "REQ ID", "value": "UR.PORT.002"}],
                relations=[relation],
            ), job)
            integ_repo.upsert_raw_artifact(cur, cid, "204", "issue", _issue(
                id=204, tracker="일감", status="진행", priority="높음", relations=[relation],
            ), job)
            now = datetime.now(UTC)
            integ_repo.finish_sync_job(cur, job, "SUCCEEDED", {}, now, now)
            standard.promote_connection(cur, conn, embedding_port())
        res = client.get(
            f"/api/projects/{PID}/issues?connectionId={cid}&size=50",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200, res.text
        by_key = {i["key"]: i for i in res.json()["content"]}
        assert by_key["RM-203"]["tracker"] == "일감"
        assert by_key["RM-203"]["requirementRefs"] == ["UR.PORT.002"]
        assert by_key["RM-203"]["relations"] == []  # 관계는 출발점(204) 쪽에만 싣는다
        assert by_key["RM-204"]["relations"] == [{"type": "precedes", "issueKey": "RM-203"}]
    finally:
        with tx() as cur:
            cur.execute("delete from issue where tool_connection_id = %s", (cid,))
            cur.execute("delete from raw_artifact where tool_connection_id = %s", (cid,))
            cur.execute("delete from sync_job where tool_connection_id = %s", (cid,))
            cur.execute("delete from tool_connection where id = %s", (cid,))
