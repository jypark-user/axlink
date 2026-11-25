# ruff: noqa: E501
"""B 그룹: 도구 연결·수집 (UC-010 ~ UC-012) 예제 시나리오.

도구 원천은 재생기(tests/fixtures/im009/replay.py)다. 기록 모드는 replay 이고 실연동 검증을
대신하지 않는다. 기대 결과는 IM-002 v0.2.4 그대로라 현재 구현과 다른 곳은 실패로 남는다.
"""

from __future__ import annotations

import threading
import time

import pytest

from app import scheduler
from app.db import fetch_all, fetch_one, tx
from app.integration import repository as integ_repo
from tests.fixtures.im009 import data as d
from tests.fixtures.im009.replay import BULK_TARGET, Faults, ReplaySource, install, tool_base
from tests.scenarios.conftest import TARGET_URL, auth

pytestmark = pytest.mark.db

SECRET = "replay-token"


@pytest.fixture
def replay(monkeypatch, s0) -> ReplaySource:
    return install(monkeypatch, ReplaySource(state="S0", files=s0.files))


def _sync(target, s0, con_tid: str, acc: str = "TD-ACC-V1", full: bool = False) -> dict:
    url = f"/api/connections/{s0.ids[con_tid]}/sync"
    body = {"kind": "BACKFILL"} if full else None
    res = target.post(url, json=body, headers=auth(s0.tokens[acc]))
    assert res.status_code == 202, res.text
    return res.json()


def _counts(cur, pid: str) -> dict:
    row = fetch_one(
        cur,
        """
        select (select count(*) from issue where project_id = %(p)s) as issues,
               (select count(*) from risk where project_id = %(p)s) as risks,
               (select count(*) from code_change where project_id = %(p)s) as changes,
               (select count(*) from milestone where project_id = %(p)s) as milestones,
               (select count(*) from trace_link where project_id = %(p)s) as links,
               (select count(*) from requirement where project_id = %(p)s) as requirements
        """,
        {"p": pid},
    )
    return dict(row)


def _conn_body(name: str, target: str, tool: str = "GITHUB") -> dict:
    return {
        "tool": tool,
        "name": name,
        "baseUrl": tool_base(tool, "https://api.github.com"),
        "targetResource": target,
        "credential": {"accessToken": "ghp_replayTokenABCDEF123456"},
    }


# ------------------------------------------------------------------ UC-010


def test_UC_010_S02_Redmine_REST_비활성(target, s0, replay):
    """REST 꺼진 Redmine 확인 → 「REST 웹 서비스 비활성」 안내, 상태 확인 전 (AC-010-2)."""
    replay.faults = Faults(rest_disabled=True)
    body = {
        "tool": "REDMINE",
        "name": "REST 꺼짐",
        "baseUrl": tool_base("REDMINE", "https://redmine.example.test"),
        # TD-CON-2 와 같은 서버·대상은 중복으로 막힌다(DEF-V013). 다른 식별자를 쓴다
        "targetResource": "rest-off-project",
        "credential": {"accessToken": "key"},
    }
    made = target.post(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/connections",
        json=body,
        headers=auth(s0.tokens["TD-ACC-V1"]),
    )
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    res = target.post(f"/api/connections/{cid}/test", headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code >= 400, res.text
    assert "REST" in res.text, f"REST 비활성을 구분해 안내하지 않는다: {res.text[:200]}"
    row = target.get(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/connections", headers=auth(s0.tokens["TD-ACC-V1"])
    ).json()
    assert next(c for c in row if c["id"] == cid)["status"] == "DRAFT"


def test_UC_010_S03_자격증명_비노출(target, s0):
    """연결 조회·목록에 원문 없음, DB 는 암호문 (AC-010-1)."""
    rows = target.get(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/connections", headers=auth(s0.tokens["TD-ACC-V1"])
    ).json()
    text = str(rows)
    assert SECRET not in text
    for c in rows:
        assert c["credentialMasked"] is None or len(c["credentialMasked"]) <= 8
    with tx() as cur:
        stored = fetch_all(
            cur,
            "select auth_encrypted from tool_connection where project_id = %s",
            (s0.ids["TD-PRJ-1"],),
        )
    assert stored and all(SECRET not in (r["auth_encrypted"] or "") for r in stored)


def test_UC_010_S04_다른_업체_연결_변경(target, s0):
    """V2 가 TD-CON-1 설정 변경·삭제·자격증명 조회 → 거절. C1 은 성공 (AC-010-4)."""
    cid = s0.ids["TD-CON-1"]
    v2, c1 = auth(s0.tokens["TD-ACC-V2"]), auth(s0.tokens["TD-ACC-C1"])
    assert (
        target.patch(f"/api/connections/{cid}", json={"name": "바꿈"}, headers=v2).status_code
        == 403
    )
    assert target.delete(f"/api/connections/{cid}", headers=v2).status_code == 403
    rows = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/connections", headers=v2).json()
    con1 = next(c for c in rows if c["id"] == cid)
    assert con1["credentialMasked"] is None, "다른 업체 소유 연결의 자격증명 힌트가 보인다"
    ok = target.patch(f"/api/connections/{cid}", json={"name": "TD-CON-1"}, headers=c1)
    assert ok.status_code == 200, ok.text


def test_UC_010_S05_둘째_GitHub_연결_중복(target, s0, replay):
    """같은 도구 둘째 연결은 소유 업체가 보이고, 같은 서버·대상은 중복 거절 (AC-010-5)."""
    rows = target.get(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/connections", headers=auth(s0.tokens["TD-ACC-C1"])
    ).json()
    con3 = next(c for c in rows if c["id"] == s0.ids["TD-CON-3"])
    assert con3["ownerOrgName"] == d.ORGS["TD-ORG-V2"].name
    dup = target.post(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/connections",
        json=_conn_body("중복", d.CONNECTIONS["TD-CON-1"].target),
        headers=auth(s0.tokens["TD-ACC-V2"]),
    )
    assert dup.status_code == 409, dup.text


def test_UC_010_S09_소유_업체_변경(target, s0):
    """C1 이 TD-CON-1 의 소유 업체를 참여 업체 V2(라온시스템)로 바꾼다 → 목록에 새 소유 업체, 변경 이력.
    용역사는 바꿀 수 없고, 참여하지 않는 업체(V3)로는 넘길 수 없다. 끝에 V1 로 되돌린다 (AC-010-8)."""
    cid, pid = s0.ids["TD-CON-1"], s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    v1_org, v2_org, v3_org = (s0.ids[k] for k in ("TD-ORG-V1", "TD-ORG-V2", "TD-ORG-V3"))
    url = f"/api/connections/{cid}/owner"
    denied = target.patch(url, json={"organizationId": v2_org}, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert denied.status_code == 403, denied.text
    outsider = target.patch(url, json={"organizationId": v3_org}, headers=c1)
    assert outsider.status_code == 400, outsider.text
    try:
        res = target.patch(url, json={"organizationId": v2_org}, headers=c1)
        assert res.status_code == 200, res.text
        assert (res.json()["ownerOrgId"], res.json()["ownerOrgName"]) == (v2_org, "라온시스템")
        listed = target.get(f"/api/projects/{pid}/connections", headers=c1).json()
        assert next(c for c in listed if c["id"] == cid)["ownerOrgName"] == "라온시스템"
        with tx() as cur:
            hist = fetch_one(
                cur,
                "select from_value, to_value, actor from entity_history "
                "where entity_type = 'TOOL_CONNECTION' and entity_id = %s and field = 'owner_org' "
                "order by created_at desc limit 1",
                (cid,),
            )
        assert (hist["from_value"], hist["to_value"]) == (v1_org, v2_org), hist
        assert hist["actor"], hist
    finally:
        back = target.patch(url, json={"organizationId": v1_org}, headers=c1)
        assert back.status_code == 200, back.text


def test_UC_010_S07_외부_장애(target, s0, replay):
    """네트워크 차단 상태에서 확인 → 네트워크 오류 안내, 성공 기록 없음 (COMMON-S09)."""
    replay.faults = Faults(unreachable=True)
    made = target.post(
        f"/api/projects/{s0.ids['TD-PRJ-9']}/connections",
        json=_conn_body("장애", "x/offline"),
        headers=auth(s0.tokens["TD-ACC-V1"]),
    ).json()
    res = target.post(f"/api/connections/{made['id']}/test", headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code >= 400, res.text
    assert "연결" in res.text or "네트워크" in res.text, res.text[:200]
    rows = target.get(
        f"/api/projects/{s0.ids['TD-PRJ-9']}/connections", headers=auth(s0.tokens["TD-ACC-V1"])
    ).json()
    assert next(c for c in rows if c["id"] == made["id"])["status"] == "DRAFT"


def test_UC_010_S08_확인_전_활성화_교체_뒤_상태(target, s0, replay, screen):
    """저장만 한 연결 활성화 → 거절. 확인 뒤 토큰 교체 → 「확인 전」 (AC-010-7).

    브라우저가 있으면 이어서 연결 관리 화면의 [수정] 양식으로 수집 대상을 바꾸고, 코드 수정 없이
    설정만으로 대상이 바뀌며 「확인 전」으로 돌아가는 것을 화면에서 확인한다(SWFR.CON.002 시연)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    made = target.post(
        f"/api/projects/{s0.ids['TD-PRJ-9']}/connections",
        json=_conn_body("새 연결", "daon/test-repo"),
        headers=v1,
    ).json()
    cid = made["id"]
    assert made["status"] == "DRAFT"
    assert (
        target.patch(
            f"/api/connections/{cid}/status", json={"status": "ACTIVE"}, headers=v1
        ).status_code
        == 400
    )
    assert target.post(f"/api/connections/{cid}/test", headers=v1).status_code == 200
    assert (
        target.patch(
            f"/api/connections/{cid}/status", json={"status": "ACTIVE"}, headers=v1
        ).json()["status"]
        == "ACTIVE"
    )
    changed = target.patch(
        f"/api/connections/{cid}",
        json={"credential": {"accessToken": "ghp_anotherToken000000"}},
        headers=v1,
    )
    assert changed.status_code == 200 and changed.json()["status"] == "DRAFT", changed.text
    if not screen:
        return
    assert target.post(f"/api/connections/{cid}/test", headers=v1).status_code == 200
    sc = screen("TD-ACC-V1")
    page = sc.page
    sc.open(f"/p/{s0.ids['TD-PRJ-9']}/connections")
    card = (
        page.locator("div")
        .filter(has_text="새 연결")
        .filter(has=page.get_by_role("button", name="수정", exact=True))
        .last
    )
    card.get_by_role("button", name="수정", exact=True).click()
    page.locator("#connResource").fill("daon/test-repo-2")
    sc.shot("대상-수정")
    page.get_by_role("dialog").get_by_role("button", name="저장", exact=True).click()
    sc.see("연결을 수정했습니다.", selector="body")
    from playwright.sync_api import expect

    expect(card).to_contain_text("daon/test-repo-2", timeout=15000)
    expect(card).to_contain_text("확인 전", timeout=15000)
    after = target.get(f"/api/connections/{cid}", headers=v1)
    if after.status_code == 200:
        body = after.json()
        assert body["targetResource"] == "daon/test-repo-2" and body["status"] == "DRAFT", body
    sc.done()


# ------------------------------------------------------------------ UC-011


def test_UC_011_S02_변경_없는_증분(target, s0, replay):
    """원천이 그대로일 때 지금 수집 → 요청 범위는 마지막 시각 이후, 이력 신규·갱신 0 (AC-011-1·2)."""  # noqa: E501
    job = _sync(target, s0, "TD-CON-1")
    assert job["status"] == "SUCCEEDED", job
    kinds = [c for c in replay.calls() if c[0] == "GITHUB" and c[1] == "issue"]
    assert kinds and kinds[-1][2], "증분 요청에 since 가 없다(전체를 다시 읽는다)"
    assert job["stats"]["skippedUnchanged"] == job["stats"]["fetched"], job["stats"]
    # 화면의 「신규·갱신」은 changed 다. upserted 는 재승격을 포함한 「반영」 건수다
    assert job["stats"]["changed"] == 0, (
        f"변경이 없는데 신규·갱신이 {job['stats']['changed']} 로 기록된다"
    )


def test_UC_011_S04_반복_재현(target, s0, replay):
    """전체 다시 ×3 → 매번 같은 건수·상태·링크·지표. 요구사항 A 지정 보존 (AC-011-4·5, COMMON-S08)."""  # noqa: E501
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        before = _counts(cur, pid)
    results = []
    for _ in range(3):
        for con in ("TD-CON-1", "TD-CON-2", "TD-CON-3"):
            job = _sync(target, s0, con, full=True)
            assert job["status"] == "SUCCEEDED", job
        with tx() as cur:
            results.append(_counts(cur, pid))
    assert results[0] == results[1] == results[2] == before, (before, results)
    reqs = target.get(
        f"/api/projects/{pid}/requirements?size=50", headers=auth(s0.tokens["TD-ACC-C1"])
    ).json()
    a = next(r for r in reqs["content"] if r["code"] == "UR.PORT.001")
    assert a["status"] == "VERIFIED"
    assert a["id"] == s0.ids["TD-REQ-A"]


def test_UC_011_S05a_인증_실패(target, s0, replay):
    """토큰 무효 → 「실패」·사유 인증, 적재 0, 기준 시각·지표 불변 (AC-011-6a)."""
    pid = s0.ids["TD-PRJ-1"]
    h = auth(s0.tokens["TD-ACC-C1"])
    before_prog = target.get(
        f"/api/projects/{pid}/progress?at={d.T0.isoformat()}", headers=h
    ).json()
    with tx() as cur:
        before = _counts(cur, pid)
    replay.faults = Faults(auth_fail=True)
    job = _sync(target, s0, "TD-CON-1")
    assert job["status"] == "FAILED", job
    assert "인증" in (job["error"] or "") or "토큰" in (job["error"] or ""), job["error"]
    assert job["stats"]["fetched"] == 0
    with tx() as cur:
        assert _counts(cur, pid) == before
    after_prog = target.get(f"/api/projects/{pid}/progress?at={d.T0.isoformat()}", headers=h).json()
    assert after_prog["representative"] == before_prog["representative"]


def test_UC_011_S05b_필수_대상_권한_없음(target, s0, replay):
    """이슈 읽기 권한 없음(TD-TOK-NOISSUE) → 「실패」, 사유에 이슈. 성공·부분 성공 아님 (AC-011-6b)."""  # noqa: E501
    replay.faults = Faults(denied_kinds={"issue"})
    job = _sync(target, s0, "TD-CON-1")
    assert job["status"] == "FAILED", (
        f"필수 대상(이슈)이 막혔는데 {job['status']} 로 기록된다: {job.get('error')}"
    )
    assert "issue" in (job["error"] or "") or "이슈" in (job["error"] or "")


def test_UC_011_S05c_선택_대상_권한_없음(target, s0, replay):
    """PR 권한 없음(TD-TOK-NOPR) → 「부분 성공」, 빠진 대상 PR, 나머지는 적재 (AC-011-6c)."""
    replay.faults = Faults(denied_kinds={"pull_request"})
    job = _sync(target, s0, "TD-CON-1", full=True)
    assert job["status"] == "SUCCEEDED", job
    assert "pull_request" in (job["error"] or ""), job["error"]
    assert job["stats"]["fetched"] > 0
    with tx() as cur:
        n = fetch_one(
            cur,
            "select count(*) as n from issue where tool_connection_id = %s",
            (s0.ids["TD-CON-1"],),
        )["n"]
    assert n >= 2  # G4·G5


def test_UC_011_S09_시작_전_연결_실패(target, s0, replay):
    """서버 응답 없음 → 「실패」·사유 네트워크, 적재 0 (AC-011-6a)."""
    replay.faults = Faults(unreachable=True)
    job = _sync(target, s0, "TD-CON-2")
    assert job["status"] == "FAILED", job
    assert job["stats"]["fetched"] == 0
    assert "연결" in (job["error"] or "") or "서버" in (job["error"] or ""), job["error"]


def _job_count(cid: str) -> int:
    with tx() as cur:
        return int(
            fetch_one(cur, "select count(*) as n from sync_job where tool_connection_id = %s",
                      (cid,))["n"]
        )


def test_UC_011_S06_동시_실행(target, s0, replay):
    """TD-CON-1 수집 회차 진행 중(장시간 응답 주입) → 지금 수집 「이미 수집 중」,
    예약 도래도 건너뜀. 진행 중이던 회차는 끝까지 돌고 잡은 그 한 건만 남는다
    (AC-011-8, COMMON-S04)."""
    cid = s0.ids["TD-CON-1"]
    url = f"/api/connections/{cid}/sync"
    v1 = auth(s0.tokens["TD-ACC-V1"])
    before = _job_count(cid)
    # 원천 이슈 목록이 5초 늦게 온다. 연결의 응답 대기 상한(10초) 안이라 회차는 성공한다
    replay.faults = Faults(delay_seconds=5)
    first: dict = {}
    runner = threading.Thread(target=lambda: first.setdefault("res", target.post(url, headers=v1)))
    runner.start()
    try:
        deadline = time.monotonic() + 20
        while not any(c[0] == "GITHUB" and c[1] == "issue" for c in replay.calls()):
            assert time.monotonic() < deadline, "첫 회차가 원천 이슈 목록을 부르지 않는다"
            time.sleep(0.2)
        # 지금 수집(수동)
        second = target.post(url, headers=v1)
        assert second.status_code == 409, f"진행 중인데 둘째 수집이 시작됐다: {second.text[:200]}"
        assert "이미 수집 중" in second.json()["message"], second.text
        # 예약 도래: 예약 수집이 같은 연결을 집어도 진행 중이면 건너뛴다(스케줄러의 한 건 처리 경로)
        with tx() as cur:
            conn = integ_repo.find_by_id(cur, cid)
        assert scheduler.sync_connection(conn) == "skipped"
    finally:
        runner.join(60)
        replay.faults = Faults()
    assert not runner.is_alive()
    res = first["res"]
    assert res.status_code == 202 and res.json()["status"] == "SUCCEEDED", res.text[:300]
    assert _job_count(cid) == before + 1, "거절된 회차의 잡이 남았다"


def _bulk_state(cid: str, pid: str) -> dict:
    with tx() as cur:
        row = fetch_one(
            cur,
            """
            select (select count(*) from raw_artifact
                     where tool_connection_id = %(c)s and object_kind = 'issue') as raw,
                   (select count(*) from issue where tool_connection_id = %(c)s) as issues,
                   (select count(*) from issue
                     where tool_connection_id = %(c)s and status = 'OPEN') as open_issues,
                   (select count(distinct status) from issue
                     where tool_connection_id = %(c)s) as statuses,
                   (select count(*) from trace_link where project_id = %(p)s) as links
            """,
            {"c": cid, "p": pid},
        )
    return dict(row)


def test_UC_011_S08_상한_초과_이어_읽기(target, s0, replay):
    """이슈 1,001건 변형 → 1회차 「부분 성공(이어 읽기)」 1,000건, 2회차 1,001건 완성, 3회차 불변
    (AC-011-10·5). 회차 상한은 종류마다 50건 × 20쪽 = 1,000건(app/integration/sync.py)."""
    pid = s0.ids["TD-PRJ-9"]
    v1 = auth(s0.tokens["TD-ACC-V1"])
    replay.faults = Faults(bulk_issues=1001)
    made = target.post(
        f"/api/projects/{pid}/connections", json=_conn_body("대량 이슈", BULK_TARGET), headers=v1
    )
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    try:
        assert target.post(f"/api/connections/{cid}/test", headers=v1).status_code == 200

        def run() -> dict:
            # 원격은 1,000건 승격·색인까지 한 요청 안에서 끝난다. 기본 60초로는 모자랄 수 있다
            wait = {"timeout": 600} if TARGET_URL else {}
            res = target.post(f"/api/connections/{cid}/sync", headers=v1, **wait)
            assert res.status_code == 202, res.text
            return res.json()

        first = run()
        assert first["status"] == "SUCCEEDED", first
        assert "이어 읽" in (first["error"] or ""), f"상한 도달이 이어 읽기로 안 남았다: {first}"
        state1 = _bulk_state(cid, pid)
        assert state1["raw"] == 1000 and state1["issues"] == 1000, state1

        second = run()
        assert second["status"] == "SUCCEEDED", second
        assert "이어 읽" not in (second["error"] or ""), second["error"]
        state2 = _bulk_state(cid, pid)
        assert state2["raw"] == 1001 and state2["issues"] == 1001, state2

        third = run()
        assert third["status"] == "SUCCEEDED", third
        assert third["stats"]["changed"] == 0, third["stats"]
        assert _bulk_state(cid, pid) == state2
    finally:
        replay.faults = Faults()
        with tx() as cur:
            for table in ("issue", "code_change", "requirement", "risk", "milestone"):
                cur.execute(f"delete from {table} where tool_connection_id = %s", (cid,))
            cur.execute("delete from raw_artifact where tool_connection_id = %s", (cid,))
            cur.execute("delete from sync_job where tool_connection_id = %s", (cid,))
            cur.execute("delete from tool_connection where id = %s", (cid,))


def test_UC_011_S07d_증분_응답에_없음(target, s0, replay):
    """증분 응답에 G5 가 없어도(변화 없음) 삭제 표시 없음 (AC-011-7)."""
    before = target.get(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/issues?size=100", headers=auth(s0.tokens["TD-ACC-C1"])
    ).json()
    g5 = next(i for i in before["content"] if i["key"] == "GH-5")
    job = _sync(target, s0, "TD-CON-1")
    assert job["status"] == "SUCCEEDED"
    after = target.get(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/issues?size=100", headers=auth(s0.tokens["TD-ACC-C1"])
    ).json()
    g5_after = next(i for i in after["content"] if i["key"] == "GH-5")
    assert g5_after["status"] == g5["status"]
    assert "삭제" not in str(g5_after)


def _source_state(cid: str, pid: str) -> dict:
    """원천 확인 불가·실패 뒤 보존을 볼 표준 모델 상태. 행 수와 추적관계, 원본 커서."""
    with tx() as cur:
        row = fetch_one(
            cur,
            """
            select (select count(*) from issue where tool_connection_id = %(c)s) as issues,
                   (select count(*) from raw_artifact where tool_connection_id = %(c)s
                     and object_kind = 'issue') as raw_issues,
                   (select count(*) from trace_link where project_id = %(p)s) as links,
                   (select last_sync_cursor from tool_connection where id = %(c)s) as cursor,
                   (select last_synced_at from tool_connection where id = %(c)s) as synced
            """,
            {"c": cid, "p": pid},
        )
    return dict(row)


def _g5(target, s0) -> dict:
    res = target.get(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/issues?size=100", headers=auth(s0.tokens["TD-ACC-C1"])
    ).json()
    return next(i for i in res["content"] if i["key"] == "GH-5")


def test_UC_011_S07a_실제_삭제(target, s0, replay):
    """G5 가 원천에서 사라진 전체 수집. 삭제를 확정할 도구 근거(DEC-18)가 없으므로 G5 와
    추적관계는 그대로 남고 삭제로 표시되지 않는다 (AC-011-7)."""
    cid, pid = s0.ids["TD-CON-1"], s0.ids["TD-PRJ-1"]
    before, g5 = _source_state(cid, pid), _g5(target, s0)
    replay.faults = Faults(drop_issue_numbers={5})
    try:
        job = _sync(target, s0, "TD-CON-1", full=True)
    finally:
        replay.faults = Faults()
    assert job["status"] == "SUCCEEDED", job
    after = _source_state(cid, pid)
    assert after["issues"] == before["issues"], (before, after)
    assert after["links"] == before["links"], (before, after)
    g5_after = _g5(target, s0)
    assert g5_after["status"] == g5["status"]
    assert "삭제" not in str(g5_after)
    assert g5_after["sourceUnverified"] is True, "응답에 없던 G5 가 「원천 확인 불가」로 표시되지 않았다"
    others = [i for i in target.get(
        f"/api/projects/{pid}/issues?size=100", headers=auth(s0.tokens["TD-ACC-C1"])
    ).json()["content"] if i["key"] != "GH-5"]
    assert not any(i["sourceUnverified"] for i in others), "응답에 있던 이슈까지 표시됐다"
    # 원천에 다시 나타나면 표시가 지워진다
    assert _sync(target, s0, "TD-CON-1", full=True)["status"] == "SUCCEEDED"
    assert _g5(target, s0)["sourceUnverified"] is False


def test_UC_011_S07b_권한_부족_404(target, s0, replay):
    """이슈 권한이 빠진 토큰으로 전체 수집 → 필수 대상 실패. 기존 이슈·추적관계는 보존되고
    삭제 표시 없음 (AC-011-6b·7)."""
    cid, pid = s0.ids["TD-CON-1"], s0.ids["TD-PRJ-1"]
    before, g5 = _source_state(cid, pid), _g5(target, s0)
    replay.faults = Faults(denied_kinds={"issue"})
    try:
        job = _sync(target, s0, "TD-CON-1", full=True)
    finally:
        replay.faults = Faults()
    assert job["status"] == "FAILED", job
    assert "issue" in (job["error"] or "") or "이슈" in (job["error"] or ""), job["error"]
    after = _source_state(cid, pid)
    assert (after["issues"], after["links"]) == (before["issues"], before["links"])
    assert after["cursor"] == before["cursor"], "실패한 회차가 변경분 기준 시각을 옮겼다"
    assert _g5(target, s0)["status"] == g5["status"]
    assert _g5(target, s0)["sourceUnverified"] is False, "권한이 빠진 회차가 확인 불가로 표시했다"


def test_UC_011_S07c_일시_조회_실패(target, s0, replay):
    """원천 조회가 5xx 로 실패한 전체 수집 → 「실패」. 삭제 표시 없음, 데이터·기준 시각 보존
    (AC-011-7)."""
    cid, pid = s0.ids["TD-CON-1"], s0.ids["TD-PRJ-1"]
    before, g5 = _source_state(cid, pid), _g5(target, s0)
    replay.faults = Faults(unreachable=True)
    try:
        job = _sync(target, s0, "TD-CON-1", full=True)
    finally:
        replay.faults = Faults()
    assert job["status"] == "FAILED", job
    after = _source_state(cid, pid)
    assert (after["issues"], after["links"]) == (before["issues"], before["links"])
    assert after["cursor"] == before["cursor"]
    assert "삭제" not in str(_g5(target, s0)) and _g5(target, s0)["status"] == g5["status"]
    assert _g5(target, s0)["sourceUnverified"] is False, "실패한 회차가 확인 불가로 표시했다"


def test_UC_011_S10_중간_실패_재시도(target, s0, replay):
    """이슈 5건 중 4번째에서 응답이 끊김 → 1회차 「실패」, 기준 시각·대표 진척률 불변, 재개 지점(다시
    시도)이 남는다. 다시 시도하면 중복·누락 없이 원천과 같다 (AC-011-9, DEC-16)."""
    cid, pid = s0.ids["TD-CON-1"], s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    prog = f"/api/projects/{pid}/progress?at={d.T0.isoformat()}"
    before, before_prog = _source_state(cid, pid), target.get(prog, headers=c1).json()
    replay.faults = Faults(cut_after=3)
    try:
        job = _sync(target, s0, "TD-CON-1", full=True)
    finally:
        replay.faults = Faults()
    assert job["status"] == "FAILED", job
    assert job["retryable"] is True, job
    mid = _source_state(cid, pid)
    assert mid["cursor"] == before["cursor"], "실패한 회차가 변경분 기준 시각을 옮겼다"
    assert target.get(prog, headers=c1).json()["representative"] == before_prog["representative"]

    res = target.post(f"/api/sync-jobs/{job['id']}/retry", headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code == 202, res.text
    again = res.json()
    assert again["status"] == "SUCCEEDED", again
    after = _source_state(cid, pid)
    # 원본은 원천의 이슈 수 그대로, 표준 모델(일반 이슈)은 회차 전과 같다
    assert after["raw_issues"] == before["raw_issues"] == len(d.GITHUB_ISSUES_CON1), after
    assert after["issues"] == before["issues"], (before, after)
    with tx() as cur:
        dup = fetch_one(
            cur,
            "select count(*) - count(distinct external_id) as n from issue "
            "where tool_connection_id = %s",
            (cid,),
        )["n"]
    assert dup == 0, "다시 시도 뒤 같은 원본이 두 번 들어갔다"
    assert after["links"] == before["links"]


def test_UC_011_S11_GitHub_종류별_필드(target, s0):
    """TD-CMT-1 메시지·변경 파일, TD-PR-1 본문·병합·연결 이슈, G1 라벨·마일스톤, TD-MS-5 기한·닫힌 날 (AC-011-11)."""  # noqa: E501
    cid = s0.ids["TD-CON-1"]
    with tx() as cur:
        raw = {
            r["external_id"]: r["payload_jsonb"]
            for r in fetch_all(
                cur,
                "select external_id, payload_jsonb from raw_artifact where tool_connection_id = %s",
                (cid,),
            )
        }
        cmt1 = fetch_one(
            cur,
            "select * from code_change where tool_connection_id = %s and ref_name = %s",
            (cid, d.COMMITS[0].sha),
        )
        ms5 = fetch_one(
            cur, "select * from milestone where tool_connection_id = %s and title = 'M-a'", (cid,)
        )
        pr1 = fetch_one(
            cur,
            "select * from code_change where tool_connection_id = %s and external_id = 'pull_request:6'",  # noqa: E501
            (cid,),
        )
    assert cmt1 is not None and cmt1["title"].startswith("feat(auth): 통합 로그인 구현")
    assert raw[f"commit:{d.COMMITS[0].sha}"]["files"][0]["filename"] == "src/auth/login.py"
    assert pr1 is not None and pr1["state"] == "MERGED"
    assert raw["pull_request:6"]["body"] == "Closes #4"
    assert raw["issue:1"]["labels"][0]["name"] == "유형: 요구사항"
    assert raw["issue:1"]["milestone"]["title"] == "M-a"
    assert ms5 is not None and str(ms5["due_on"]) == "2026-05-31" and ms5["state"] == "CLOSED"
    assert ms5["closed_at"] is not None
    # PR-1 → 이슈 G4 연결(구조적, 도구가 만든 관계)
    with tx() as cur:
        link = fetch_one(
            cur,
            """
            select 1 from trace_link l join code_change c on c.id = l.from_id
             where l.project_id = %s and c.external_id = 'pull_request:6' and l.to_type = 'ISSUE'
            """,
            (s0.ids["TD-PRJ-1"],),
        )
    assert link is not None, "PR-1 의 Closes #4 가 이슈 G4 연결로 남지 않았다"


def test_UC_011_S12_Redmine_종류별_필드(target, s0):
    """R4 트래커·우선순위·버전·이슈관계, R7 리스크, R1 커스텀 필드, TD-MS-1 기한·닫힌 날 (AC-011-12)."""  # noqa: E501
    cid = s0.ids["TD-CON-2"]
    pid = s0.ids["TD-PRJ-1"]
    with tx() as cur:
        raw = {
            r["external_id"]: r["payload_jsonb"]
            for r in fetch_all(
                cur,
                "select external_id, payload_jsonb from raw_artifact where tool_connection_id = %s",
                (cid,),
            )
        }
        r4 = fetch_one(
            cur, "select * from issue where tool_connection_id = %s and external_id = '204'", (cid,)
        )
        r7 = fetch_one(
            cur,
            "select * from risk where project_id = %s and title = %s",
            (pid, "외부 기관 일정 미확정"),
        )
        rel = fetch_one(
            cur,
            """
            select 1 from trace_link l
              join issue a on a.id = l.from_id
              join issue b on b.id = l.to_id
             where l.project_id = %s and a.external_id = '204' and b.external_id = '203'
            """,
            (pid,),
        )
        r1_link = fetch_one(
            cur,
            """
            select 1 from trace_link l join issue a on a.id = l.from_id
             where l.project_id = %s and a.external_id = '201'
               and l.to_type = 'REQUIREMENT' and l.to_id = %s
            """,
            (pid, s0.ids["TD-REQ-A"]),
        )
        ms1 = fetch_one(
            cur, "select * from milestone where tool_connection_id = %s and title = '1차'", (cid,)
        )
    assert raw["204"]["tracker"]["name"] == "일감" and raw["204"]["fixed_version"]["name"] == "2차"
    assert r4 is not None and r4["source_priority"] == "높음"
    assert rel is not None, "R4 → R3 이슈관계(선행)가 추적관계로 남지 않았다"
    assert r7 is not None and r7["severity"] == "CRITICAL"
    assert r1_link is not None, "R1 커스텀 필드 UR.PORT.001 이 요구사항 A 로 이어지지 않았다"
    assert ms1 is not None, "Redmine 버전 1차가 표준 모델(milestone)에 없다"
    assert str(ms1["due_on"]) == "2026-04-30" and ms1["state"] == "CLOSED"


# ------------------------------------------------------------------ UC-012


def test_UC_012_S01_리스크_트래커_매핑(target, s0, replay):
    """리스크 트래커 「위험」 설정 → 전체 다시 수집 → 그 트래커 이슈가 리스크로, 원시본은 그대로 (AC-012-1·3)."""  # noqa: E501
    replay.faults = Faults(tracker_rename={"리스크": "위험"})
    cid = s0.ids["TD-CON-2"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    res = target.patch(
        f"/api/connections/{cid}/mapping",
        json={"mappingRules": {"riskTracker": "위험", "reqIdField": "요구사항 ID"}},
        headers=c1,
    )
    assert res.status_code == 200, res.text
    job = _sync(target, s0, "TD-CON-2", acc="TD-ACC-C1", full=True)
    assert job["status"] == "SUCCEEDED", job
    with tx() as cur:
        risks = fetch_all(
            cur, "select title from risk where project_id = %s", (s0.ids["TD-PRJ-1"],)
        )
        raw207 = fetch_one(
            cur,
            "select payload_jsonb from raw_artifact where tool_connection_id = %s and external_id = '207'",  # noqa: E501
            (cid,),
        )
    assert {r["title"] for r in risks} >= {"외부 기관 일정 미확정", "서버 반입 지연"}
    assert raw207["payload_jsonb"]["tracker"]["name"] == "위험", "원시본의 트래커 이름이 바뀌었다"


def test_UC_012_S02_주기_변경(target, s0):
    """주기 30분, 스냅샷 06:00 → 다음 예약 반영 (AC-012-4)."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    res = target.put(
        f"/api/projects/{pid}/schedule",
        json={
            "syncIntervalMinutes": 30,
            "snapshotTime": "06:00",
            "snapshotIntervalHours": 24,
        },
        headers=c1,
    )
    assert res.status_code == 200, res.text
    got = target.get(f"/api/projects/{pid}/schedule", headers=c1).json()
    assert got["syncIntervalMinutes"] == 30 and got["snapshotTime"] == "06:00"
    from app.scheduler import _load_schedules

    with tx() as cur:
        sched = next(s for s in _load_schedules(cur) if s.project_id == pid)
    assert sched.sync_interval_minutes == 30 and str(sched.snapshot_at)[:5] == "06:00"


def test_UC_012_S03_용역사_시도(target, s0):
    """V1 이 사업 주기 변경 / V2 연결 매핑 변경 → 거절 (COMMON-S02)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    res = target.put(
        f"/api/projects/{s0.ids['TD-PRJ-1']}/schedule",
        json={
            "syncIntervalMinutes": 60,
            "snapshotTime": "07:00",
            "snapshotIntervalHours": 24,
        },
        headers=v1,
    )
    assert res.status_code == 403, res.text
    res = target.patch(
        f"/api/connections/{s0.ids['TD-CON-3']}/mapping",
        json={"mappingRules": {"riskTracker": "x"}},
        headers=v1,
    )
    assert res.status_code == 403, res.text


def test_UC_012_S04_WBS_경로_변경(target, s0):
    """TD-CON-1 의 수집 파일 경로를 docs/plan/WBS.xlsx 로 → 연결별 설정이 저장된다 (AC-012-1·5)."""
    c1 = auth(s0.tokens["TD-ACC-C1"])
    res = target.patch(
        f"/api/connections/{s0.ids['TD-CON-1']}/mapping",
        json={"mappingRules": {"collectFiles": "docs/plan/WBS.xlsx=PROJECT_PLAN"}},
        headers=c1,
    )
    assert res.status_code == 200, (
        f"수집 파일 경로를 연결별로 설정할 수 없다(서버 전역 설정): {res.status_code} {res.text[:200]}"  # noqa: E501
    )


def test_UC_012_S05_모르는_키(target, s0):
    """오타 키 → 거절·허용 키 안내 (AC-012-2)."""
    res = target.patch(
        f"/api/connections/{s0.ids['TD-CON-2']}/mapping",
        json={"mappingRules": {"riskTrakcer": "리스크"}},
        headers=auth(s0.tokens["TD-ACC-C1"]),
    )
    assert res.status_code == 400, res.text
    assert "riskTracker" in res.text, "허용 키를 안내하지 않는다"
