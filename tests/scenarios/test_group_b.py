"""B 그룹: 도구 연결·수집 (UC-010 ~ UC-012) 예제 시나리오.

도구 원천은 재생기(tests/fixtures/im009/replay.py)다. 기록 모드는 replay 이고 실연동 검증을
대신하지 않는다. 기대 결과는 IM-007 v0.2.4 그대로라 현재 구현과 다른 곳은 실패로 남는다.
"""

from __future__ import annotations

import pytest

from app.db import fetch_all, fetch_one, tx
from tests.fixtures.im009 import data as d
from tests.fixtures.im009.replay import Faults, ReplaySource, install, tool_base
from tests.scenarios.conftest import auth

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


def test_UC_010_S08_확인_전_활성화_교체_뒤_상태(target, s0, replay):
    """저장만 한 연결 활성화 → 거절. 확인 뒤 토큰 교체 → 「확인 전」 (AC-010-7)."""
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


@pytest.mark.skip(reason="동시 실행은 장시간 응답 주입과 둘째 호출이 필요하다. 5174 에서 따로 돈다")
def test_UC_011_S06_동시_실행(target, s0):
    """같은 연결 수집 중 새 수집 → 「이미 수집 중」 (AC-011-8)."""


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
