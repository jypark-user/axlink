# ruff: noqa: E501
"""E 그룹: 현황 조회 (UC-040 ~ UC-043) 예제 시나리오.

S0 에서 시작해 UC-040-S01 이 S0r(TD-RR-1 등록)을 만들고, 다섯 축·일정 줄·이슈 조회를 T0 기준으로
본다. 스냅샷 추이(UC-041-S06)는 S0a → S1 전이가 필요해 맨 뒤에 돈다. DEC-01·17 과
브라우저·실모델 시나리오는 보류한다. 값은 IM-005A 7 절의 독립 계산값과 비교한다.
"""

from __future__ import annotations

import os
import re

import pytest

from tests.fixtures.im009 import data as d
from tests.fixtures.im009.replay import Faults, ReplaySource, install, tool_base
from tests.fixtures.im009.seed import PASSWORD
from tests.scenarios.conftest import TARGET_URL, auth

pytestmark = pytest.mark.db

T0 = d.T0.isoformat()


@pytest.fixture
def replay(monkeypatch, s0) -> ReplaySource:
    return install(monkeypatch, ReplaySource(state="S0", files=s0.files))


def _at_t0(monkeypatch) -> None:
    """사업 시계를 T0 09:00(KST) 로 돌린다. 시험 프로세스 안 실행에서만 서버에 닿는다."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.common import clock

    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 9, 15, 9, 0, tzinfo=ZoneInfo("Asia/Seoul")))


def _get(target, s0, path: str, acc="TD-ACC-C1"):
    res = target.get(path, headers=auth(s0.tokens[acc]))
    assert res.status_code == 200, (path, res.status_code, res.text[:200])
    return res.json()


def _spec(measure: str, dims: list[str], scope: list[str], template: str = "BAR_CHART", title: str = "TST") -> dict:
    return {
        "template": template, "title": title,
        "query": {"measure": measure, "dimensions": dims, "filters": [], "projectScope": scope, "limit": None},
        "options": {"unit": None, "sort": "desc", "threshold": None, "stacked": None, "showLegend": None, "compareWithPrevious": None, "columns": None},
    }


def _preview(target, s0, measure: str, dims: list[str], prj="TD-PRJ-1", template="STAT_CARD") -> dict:
    res = target.post("/api/widgets/preview", json={"spec": _spec(measure, dims, [s0.ids[prj]], template)}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, (measure, res.text[:200])
    return res.json()


def _total(body: dict):
    return (body.get("total") or {}).get("values", {}).get("value")


# ------------------------------------------------------------------ UC-040


def test_UC_053_S01_미처리_건수(target, s0, screen):
    """S0 → S0r: 목록·현황 머리줄 미처리 0 → 1, 머리줄에서 요청 목록으로 (AC-053-1). 화면 시나리오."""
    if not screen:
        pytest.skip("화면 시나리오. 원격 대상 + AXLINK_BROWSER_CHROME 에서 돈다")
    pid, name = s0.ids["TD-PRJ-1"], d.PROJECTS["TD-PRJ-1"].name
    rows = {p["id"]: p for p in _get(target, s0, "/api/projects?size=100")["content"]}
    assert rows[pid]["openReviewRequestCount"] == 0, rows[pid]["openReviewRequestCount"]
    sc = screen("TD-ACC-C1")
    sc.open("/projects").see(name)
    assert "요청" not in sc.row(name), sc.row(name)
    sc.open(f"/p/{pid}/dashboard").see("미처리 확인 요청 0건")
    sc.shot("요청_전")
    s0.s0r()
    sc.open("/projects").see(name)
    assert "요청 1" in sc.row(name), sc.row(name)
    sc.open(f"/p/{pid}/dashboard").see("미처리 확인 요청 1건")
    sc.page.get_by_test_id("open-review-count").click()
    sc.page.wait_for_url(re.compile(r"/reviews"))
    sc.see(d.REVIEW_REQUEST_TD_RR_1["title"])
    sc.done()


def test_UC_040_S01_세_사업_목록(target, s0, screen):
    """S0r: PRJ-1 진척 30.0%·편차 −36.9%p·미처리 1·리스크 1·승인 1/5(DEC-12, WBS 산출물 기준). PRJ-3 지표 「—」·미처리 0 (AC-040-1·2·3·4)."""
    if "TD-RR-1" not in s0.ids:  # 화면 실행에서는 UC-053-S01 이 S0r 을 만든다
        s0.s0r()
    rows = {p["id"]: p for p in _get(target, s0, "/api/projects?size=100")["content"]}
    p1, p3, p9 = rows[s0.ids["TD-PRJ-1"]], rows[s0.ids["TD-PRJ-3"]], rows[s0.ids["TD-PRJ-9"]]
    assert s0.ids["TD-PRJ-2"] not in rows  # C1 은 자기 조직 사업만
    problems: list[str] = []
    if p1["openReviewRequestCount"] != 1:
        problems.append(f"미처리 요청 {p1['openReviewRequestCount']} (기대 1)")
    if p1["openRiskCount"] != 1:
        problems.append(f"열린 리스크 {p1['openRiskCount']} (기대 1)")
    if (p1["requiredWorkProductApproved"], p1["requiredWorkProductTotal"]) != (1, 5):
        problems.append(f"승인 {p1['requiredWorkProductApproved']}/{p1['requiredWorkProductTotal']} (기대 1/5)")
    rep_key = next((k for k in p1 if "progress" in k.lower() or "representative" in k.lower()), None)
    if rep_key is None:
        problems.append(f"목록에 대표 진척률·편차 칸이 없다: {sorted(p1)}")
    elif round((p1[rep_key] or 0) * 100, 1) != 30.0:
        problems.append(f"대표 진척률 {p1[rep_key]} (기대 0.3000)")
    if p3["openReviewRequestCount"] != 0:
        problems.append(f"PRJ-3 미처리 {p3['openReviewRequestCount']}")
    assert p9["id"]
    assert not problems, problems
    _ui_UC_040_S01(screen, s0)


def test_UC_040_S02_용역사_목록(target, s0):
    """V1 목록 → TD-PRJ-1·9 만 (AC-040-1)."""
    rows = _get(target, s0, "/api/projects?size=100", acc="TD-ACC-V1")["content"]
    assert {p["id"] for p in rows} == {s0.ids["TD-PRJ-1"], s0.ids["TD-PRJ-9"]}


def test_UC_040_S03_현황과_일치(target, s0):
    """목록 값 vs 현황 카드 값 (AC-040-2)."""
    rows = {p["id"]: p for p in _get(target, s0, "/api/projects?size=100")["content"]}
    p1 = rows[s0.ids["TD-PRJ-1"]]
    risk = _preview(target, s0, "open_risk_count", [])
    assert _total(risk) == p1["openRiskCount"], (_total(risk), p1["openRiskCount"])
    prog = _get(target, s0, f"/api/projects/{s0.ids['TD-PRJ-1']}/progress?at={T0}")
    rep_key = next((k for k in p1 if "progress" in k.lower() or "representative" in k.lower()), None)
    assert rep_key is not None, "목록에 진척 칸이 없어 현황 카드와 비교할 수 없다"
    assert round(p1[rep_key], 4) == round(prog["representative"], 4)


def test_UC_040_S04_일정_준수_칸(target, s0, monkeypatch):
    """T0 목록의 일정 준수 칸 1/3 (33.3%). 대상 MS-1·MS-2·MS-5, 달성 MS-1 (AC-040-5, DEC-01 (a), IM-005A 7.1).

    목록은 오늘 날짜로 센다. 시험 프로세스 안에서는 사업 시계를 T0 로 돌려 본다. 원격은 대상 서버
    시계가 T0 인 격리 인스턴스(AXLINK_TARGET_CLOCK_T0=1)에서만 돈다."""
    if TARGET_URL and os.environ.get("AXLINK_TARGET_CLOCK_T0") != "1":
        pytest.skip("목록은 서버의 오늘로 센다. 원격 대상은 시계가 T0 인 격리 인스턴스에서만 본다")
    _at_t0(monkeypatch)
    rows = {p["id"]: p for p in _get(target, s0, "/api/projects?size=100")["content"]}
    p1, p3 = rows[s0.ids["TD-PRJ-1"]], rows[s0.ids["TD-PRJ-3"]]
    assert (p1["scheduleComplianceAchieved"], p1["scheduleComplianceTotal"]) == (1, 3), p1
    assert round(p1["scheduleCompliance"], 4) == 0.3333
    # 마일스톤이 없는 사업은 산출 불가(0% 가 아니다)
    assert p3["scheduleCompliance"] is None and p3["scheduleComplianceTotal"] == 0


def test_UC_040_S05_조회_실패_구분(target, s0, screen, monkeypatch):
    """한 사업의 진척 집계가 실패해도 목록은 뜨고 그 칸만 「조회 실패」(「-」와 다름) (E2, DEF-V044).

    API: 시험 프로세스 안 실행에서 TD-PRJ-3 의 집계만 실패시킨다(원격 서버에는 닿지 않아 원격은 건너뛴다).
    화면: 브라우저가 받은 목록 응답에서 TD-PRJ-3 을 집계 실패로 바꿔 넣고 표시를 본다."""
    from tests.scenarios.conftest import TARGET_URL

    p1, p3 = s0.ids["TD-PRJ-1"], s0.ids["TD-PRJ-3"]
    if not TARGET_URL:
        from app.dashboard import service as dashboard_service

        real = dashboard_service.compute

        def broken(cur, pid, today):
            if str(pid) == p3:
                cur.execute("select 1/0")  # 질의 실패: 저장점이 없으면 트랜잭션 전체가 깨진다
            return real(cur, pid, today)

        monkeypatch.setattr(dashboard_service, "compute", broken)
        res = target.get("/api/projects?size=100", headers=auth(s0.tokens["TD-ACC-C1"]))
        assert res.status_code == 200, res.text[:300]
        rows = {p["id"]: p for p in res.json()["content"]}
        assert rows[p3]["progressError"] is True and rows[p3]["representative"] is None
        assert rows[p1]["progressError"] is False and rows[p1]["representative"] is not None
        assert rows[p1]["openReviewRequestCount"] >= 0  # 나머지 칸은 그대로 계산된다
    if not screen:
        return
    sc = screen("TD-ACC-C1")

    def tamper(route):
        body = route.fetch().json()
        for p in body["content"]:
            if p["id"] == p3:
                p.update(representative=None, progressLevel=None, progressDeviation=None, progressError=True)
        route.fulfill(json=body)

    sc.page.route("**/api/projects?*", tamper)
    sc.open("/projects").see(d.PROJECTS["TD-PRJ-1"].name, d.PROJECTS["TD-PRJ-3"].name)
    row3 = sc.row(d.PROJECTS["TD-PRJ-3"].name)
    assert "조회 실패" in row3, row3
    assert "조회 실패" not in sc.row(d.PROJECTS["TD-PRJ-1"].name)
    assert "%" in sc.row(d.PROJECTS["TD-PRJ-1"].name)
    sc.done()


# ------------------------------------------------------------------ UC-041


def test_UC_041_S01_다섯_축_한_화면(target, s0, screen):
    """진척 30.0·계획 66.9·편차 −36.9 · 위험 처리율 50.0 · 열린 리스크 높음 1 · 제출 1/미제출 3/지연 1 · 일반 이슈 처리율 66.7 · 완료 확인율 15.0 (AC-041-1·2·3)."""
    pid = s0.ids["TD-PRJ-1"]
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")
    problems: list[str] = []
    if round(prog["representative"], 4) != 0.3:
        problems.append(f"진척 {prog['representative']}")
    if round(prog["wbsPlanned"], 4) != 0.6695:
        problems.append(f"계획선 {prog['wbsPlanned']}")
    if round(prog["wbsDeviation"], 4) != -0.3695:
        problems.append(f"편차 {prog['wbsDeviation']}")
    if round(prog["issue"]["value"], 4) != 0.6667 or (prog["issue"]["numerator"], prog["issue"]["denominator"]) != (6, 9):
        problems.append(f"일반 이슈 처리율 {prog['issue']}")
    if not prog["issue"].get("note") or not prog["wbs"].get("label"):
        problems.append("산출 근거 문장 없음")
    comp = _get(target, s0, f"/api/projects/{pid}/wbs/completion?at={T0}")
    if round(comp["completionRate"], 4) != 0.15:
        problems.append(f"완료 확인율 {comp['completionRate']}")
    deliv = _get(target, s0, f"/api/projects/{pid}/wbs/deliverables?at={T0}")["summary"]
    if (deliv["submitted"], deliv["missing"], deliv["overdue"]) != (1, 3, 1):
        problems.append(f"산출물 판정 {deliv}")
    risk_open = _preview(target, s0, "open_risk_count", ["risk_severity"])
    sev = {r["values"]["d0"]: r["values"]["value"] for r in risk_open["rows"]}
    if sev.get("HIGH", 0) + sev.get("CRITICAL", 0) != 1:
        problems.append(f"열린 리스크 높음 {sev}")
    try:
        rate = _preview(target, s0, "risk_resolution_rate", [])
        if round(_total(rate) or 0, 4) not in (0.5, 50.0):  # 다른 비율 지표처럼 % 값도 받는다
            problems.append(f"위험 처리율 {_total(rate)}")
    except AssertionError as exc:
        problems.append(f"위험 처리율 지표 없음: {str(exc)[:120]}")
    assert not problems, problems
    _ui_UC_041_S01(screen, target, s0)


def test_UC_041_S02_진척률에서_작업까지(target, s0, screen):
    """3.2 지연(40%, 미제출·지연 판정), 계획선 100%, 연결 이슈 #204 진행중, 완료 확인 없음. 3.1 확인됨.
    격차 경고는 실적 80 이상만이라(DEC-20 (b)) 3.2(40)·3.3(20) 에는 없다 (AC-041-4)."""
    pid = s0.ids["TD-PRJ-1"]
    wbs = _get(target, s0, f"/api/projects/{pid}/wbs?at={T0}")
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")
    comp = _get(target, s0, f"/api/projects/{pid}/wbs/completion?at={T0}")
    by = {i["wbsId"]: i for i in wbs["items"]}
    citems = {i["wbsId"]: i for i in comp["items"]}
    problems: list[str] = []
    if by["3.2"]["deliverableStatus"] != "OVERDUE":
        problems.append(f"3.2 판정 {by['3.2']['deliverableStatus']}")
    if by["3.2"]["planned"] != 100 or by["3.2"]["progress"] != 40:
        problems.append(f"3.2 계획선·실적 {by['3.2']['planned']}/{by['3.2']['progress']}")
    gapped = {i["wbsId"]: i["gapWarning"] for i in wbs["items"] if i.get("gapWarning")}
    if gapped:
        problems.append(f"실적 80 미만 작업에 격차 경고가 붙었다: {gapped}")
    if any(w.startswith("격차 경고") for w in wbs["warnings"]):
        problems.append(f"일정 경고 줄에 격차 경고가 있다: {wbs['warnings']}")
    if not any(str(x).startswith("3.2") for x in prog["behind"]):
        problems.append(f"계획 뒤짐에 3.2 가 없다: {prog['behind']}")
    if citems["3.1"]["completionStatus"] != "CONFIRMED" or citems["3.2"]["completionStatus"] != "NONE":
        problems.append(f"완료 확인 3.1 {citems['3.1']['completionStatus']} / 3.2 {citems['3.2']['completionStatus']}")
    if not any("204" in str(v) for v in by["3.2"].values()):
        problems.append("3.2 줄에 연결 이슈 #204(진행중)가 없다")
    assert not problems, problems
    _ui_UC_041_S02(screen, target, s0)


def test_UC_041_S03_L3_추정(target, s0):
    """TD-PRJ-2: 일정 줄 = 날짜 있는 이슈 6건(N6 제외), 진척도 100·100·50·30·0·100. 대표 진척률은
    이슈 기반 추정 진척률 54.3% (100+100+50+30+0+0+100)/7, 결측 1건(N6). 해결률 3/7 은 별도 지표
    (AC-041-5, DEC-17 2026-11-16)."""
    pid = s0.ids["TD-PRJ-2"]
    wbs = _get(target, s0, f"/api/projects/{pid}/wbs?at={T0}", acc="TD-ACC-C2")
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}", acc="TD-ACC-C2")
    assert wbs["source"] == "REDMINE"
    rows = [i for i in wbs["items"] if i["startDate"]]
    assert len(rows) == 6, [i["name"] for i in wbs["items"]]
    assert sorted(i["progress"] for i in rows) == [0, 30, 50, 100, 100, 100]
    assert prog["level"] == "L3" and prog["basis"] == "ISSUE_PROGRESS", prog
    assert prog["representative"] == 0.5429, prog["representative"]
    est = prog["issueEstimate"]
    assert est["label"] == "이슈 기반 추정 진척률", est
    assert (est["denominator"], est["missing"], est["value"]) == (7, 1, 0.5429), est
    # 해결률은 대표값이 아니라 별도 지표로 남는다(종료 N1·N2·N7)
    assert (prog["issue"]["numerator"], prog["issue"]["denominator"]) == (3, 7), prog["issue"]
    assert prog["issue"]["value"] != prog["representative"]
    # 추정 표시와 산출 근거 문장(DEF-V037). 같은 가중치·결측 0 처리를 밝힌다
    assert prog["estimated"] is True, prog
    note = prog["basisNote"]
    assert note.startswith("추정: WBS 가 없어 이슈 기반 추정 진척률로 산정했습니다"), note
    assert "같은 가중치" in note and "1건은 0으로 셌습니다" in note and "L1" in note, note
    assert note in prog["warnings"], prog["warnings"]
    # 사업 목록 칸도 같은 산정이다(AC-040-2)
    listed = [p for p in _get(target, s0, "/api/projects?size=50", acc="TD-ACC-C2")["content"]
              if p["id"] == pid]
    assert listed and listed[0]["representative"] == 0.5429, listed
    assert listed[0]["progressBasisNote"] == note
    # 스냅샷은 산식을 함께 적는다(V65). 옛 L3(해결률) 행과 섞지 않는다
    res = target.post(f"/api/projects/{pid}/snapshots", headers=auth(s0.tokens["TD-ACC-C2"]))
    assert res.status_code == 200, res.text
    snap = res.json()
    assert snap["representativeBasis"] == "ISSUE_PROGRESS", snap
    assert snap["representativeBasisLabel"] == "이슈 기반 추정 진척률"
    assert snap["issueEstimateMissingCount"] == 1 and snap["issueEstimatePct"] == 54.29, snap


def test_UC_041_S03b_L3_경계_진척도_전부_없음(target, s0, replay):
    """TD-PRJ-2 의 이슈가 진척도를 하나도 주지 않으면 L3 산출 불가다. 0% 가 아니고 해결률로
    대신하지 않으며 산출물로 내려가지 않는다(DEC-17). 진척도가 돌아오면 54.3% 로 돌아온다."""
    pid = s0.ids["TD-PRJ-2"]

    def resync() -> None:
        res = target.post(
            f"/api/connections/{s0.ids['TD-CON-4']}/sync", json={"kind": "BACKFILL"},
            headers=auth(s0.tokens["TD-ACC-V3"]),
        )
        assert res.status_code == 202, res.text
        assert res.json()["status"] == "SUCCEEDED", res.json()

    replay.faults = Faults(drop_done_ratio=True)
    try:
        resync()
        prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}", acc="TD-ACC-C2")
        assert prog["level"] == "L3" and prog["basis"] == "ISSUE_PROGRESS", prog
        assert prog["representative"] is None, prog["representative"]
        assert prog["estimated"] is False
        est = prog["issueEstimate"]
        assert est["value"] is None and (est["denominator"], est["missing"]) == (7, 7), est
        assert prog["basisNote"].startswith("산출 불가"), prog["basisNote"]
        assert "해결 3 / 전체 7건" in prog["basisNote"], prog["basisNote"]
        assert prog["issue"]["value"] is not None  # 해결률은 그대로 산출된다
    finally:
        replay.faults = Faults()
        resync()
    back = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}", acc="TD-ACC-C2")
    assert back["representative"] == 0.5429, back["representative"]


def test_UC_041_S04_재료_없음(target, s0, screen):
    """TD-PRJ-3: 진척 산출 안 함, 카드 데이터 없음, 스냅샷 산정 불가 (AC-041-5·6). API 부분."""
    pid = s0.ids["TD-PRJ-3"]
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")
    assert prog["representative"] is None, f"재료 없는 사업의 진척이 {prog['representative']} 로 산출됐다(DEF-V003)"
    assert prog["wbs"]["value"] is None and prog["issue"]["value"] is None
    _ui_UC_041_S04(screen, s0)


def test_UC_041_S05_수동_스냅샷(target, s0):
    """C1 지금 기록 → 오늘 행 · V1 시도 거절 · C1 어제 날짜 거절 (AC-041-7)."""
    from datetime import date, timedelta

    pid = s0.ids["TD-PRJ-1"]
    res = target.post(f"/api/projects/{pid}/snapshots", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text
    assert res.json()["representativePct"] is not None
    assert target.post(f"/api/projects/{pid}/snapshots", headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert target.post(f"/api/projects/{pid}/snapshots?at={yesterday}", headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 400
    # 같은 날 다시 기록하면 덮어쓴다(행이 늘지 않는다)
    before = len(_get(target, s0, f"/api/projects/{pid}/snapshots"))
    assert target.post(f"/api/projects/{pid}/snapshots", headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 200
    assert len(_get(target, s0, f"/api/projects/{pid}/snapshots")) == before


def test_UC_041_S09_분모_0(target, s0):
    """분모 0 인 비율 → 「산출 불가」, 0%·100% 아님 (AC-041-6). TD-PRJ-3 의 일반 이슈 처리율."""
    body = _preview(target, s0, "issue_resolution_rate", [], prj="TD-PRJ-3")
    assert _total(body) is None, f"이슈가 없는 사업의 처리율이 {_total(body)} 로 산출됐다"


def test_UC_041_S12_WBS_변형(target, s0, replay):
    """TD-PRJ-9: L2 30.3% 추정(기간 비례 × 실적, DEC-19) / MISS 3.4 해당 없음·30.0% / SUM 경고·27.3% (AC-041-3·5, AC-030-3)."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    pid = s0.ids["TD-PRJ-9"]
    replay.faults = Faults(wbs_targets={"daon/prj9"}, wbs_variant="TD-WBS-SUM", wbs_sha="5a5a5a5a" + "9" * 32)
    made = target.post(f"/api/projects/{pid}/connections", json={
        "tool": "GITHUB", "name": "PRJ-9 저장소", "baseUrl": tool_base("GITHUB", "https://api.github.com"), "targetResource": "daon/prj9",
        "credential": {"accessToken": "ghp_prj9Token000000000000"},
    }, headers=v1).json()
    cid = made["id"]
    assert target.post(f"/api/connections/{cid}/test", headers=v1).status_code == 200
    problems: list[str] = []

    def sync_with(variant: str, sha: str) -> dict:
        replay.faults = Faults(wbs_targets={"daon/prj9"}, wbs_variant=variant, wbs_sha=sha)
        job = target.post(f"/api/connections/{cid}/sync", json={"kind": "BACKFILL"}, headers=v1).json()
        assert job["status"] == "SUCCEEDED", job
        return _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")

    prog = sync_with("TD-WBS-SUM", "5a5a5a5a" + "9" * 32)
    if round(prog["representative"] or 0, 4) != 0.2727 or not any("1.1" in w for w in prog["warnings"]):
        problems.append(f"SUM: {prog['representative']} {prog['warnings']}")
    prog = sync_with("TD-WBS-MISS", "9999aaaa" + "9" * 32)
    if round(prog["representative"] or 0, 4) != 0.3:
        problems.append(f"MISS: {prog['representative']}")
    deliv = {i["wbsId"]: i for i in _get(target, s0, f"/api/projects/{pid}/wbs/deliverables?at={T0}")["items"]}
    if deliv["3.4"]["status"] != "NONE":
        problems.append(f"MISS 3.4 판정 {deliv['3.4']['status']}")
    prog = sync_with("TD-WBS-L2", "2c2c2c2c" + "9" * 32)
    if (
        prog["level"] != "L2" or prog["representative"] is None or round(prog["representative"], 4) != 0.3029
        or not prog["estimated"] or not prog["basisNote"].startswith("추정")
    ):
        problems.append(f"L2: {prog['representative']} level={prog['level']} {prog.get('basisNote')}")
    assert not problems, problems


def test_UC_041_S07_일정_준수율(target, s0, monkeypatch):
    """T0 일정 준수율 1/3 = 33.3%, 계획선 편차와 별도 지표·별도 카드 (AC-041-9, DEC-01 (a), IM-005A 7.1)."""
    pid = s0.ids["TD-PRJ-1"]
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")
    sc = prog["scheduleCompliance"]
    assert (sc["numerator"], sc["denominator"]) == (1, 3), sc
    assert round(sc["value"], 4) == 0.3333 and sc["note"], sc
    # 기준일 2026-04-15: 기한이 지난 마일스톤이 없어 산출 불가
    early = _get(target, s0, f"/api/projects/{pid}/progress?at=2026-04-15")["scheduleCompliance"]
    assert early["value"] is None and early["denominator"] == 0 and "산출 불가" in early["note"], early
    if TARGET_URL:
        return  # 카드는 서버의 오늘로 센다. 시계를 T0 로 돌릴 수 있는 프로세스 안에서만 값을 본다
    _at_t0(monkeypatch)
    card = _preview(target, s0, "schedule_compliance_rate", [])
    assert round(_total(card) or 0, 2) == 33.33, _total(card)
    variance = _preview(target, s0, "schedule_variance_pct", [])
    assert variance["measure"] != card["measure"]


def test_UC_041_S08_결함_처리율(target, s0):
    """결함 처리율 50.0%(R9 종료 ÷ R9·R10). 결함 트래커 매핑으로 가른 이슈만. 전체 11 = 일반 9 + 결함 2 (AC-041-10, DEC-02)."""
    pid = s0.ids["TD-PRJ-1"]
    problems: list[str] = []
    rate = _preview(target, s0, "defect_resolution_rate", [])
    if round(_total(rate) or 0, 4) not in (0.5, 50.0):
        problems.append(f"결함 처리율 {_total(rate)}")
    if (rate["total"]["values"].get("numerator"), rate["total"]["values"].get("denominator")) != (1, 2):
        problems.append(f"결함 처리율 분자·분모 {rate['total']['values']}")
    if "결함 트래커" not in (rate.get("basis") or ""):
        problems.append(f"산출 근거에 결함 기준이 없다: {rate.get('basis')}")
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")
    if not prog.get("defect") or (prog["defect"]["numerator"], prog["defect"]["denominator"]) != (1, 2):
        problems.append(f"진척 응답의 결함 {prog.get('defect')}")
    # 포함 관계: 전체 이슈(결함 포함)를 종류로 나누면 일반 9·결함 2, 전체는 따로 센 11
    kinds = _preview(target, s0, "all_issue_count", ["issue_kind"], template="STAT_CARD")
    by_kind = {r["values"]["d0"]: r["values"]["value"] for r in kinds["rows"]}
    if by_kind != {"GENERAL": 9, "DEFECT": 2} or _total(kinds) != 11:
        problems.append(f"종류별 {by_kind} 전체 {_total(kinds)} (기대 일반 9·결함 2·전체 11)")
    if _total(_preview(target, s0, "issue_count", [])) != 9 or _total(_preview(target, s0, "defect_count", [])) != 2:
        problems.append("일반 이슈 9·결함 2 가 따로 안 나온다")
    # 매핑이 없는 사업(TD-PRJ-2, TD-CON-4 에 결함 트래커 없음): 산출 불가와 이유, 일반 이슈 = 전체
    pid2 = s0.ids["TD-PRJ-2"]
    prog2 = _get(target, s0, f"/api/projects/{pid2}/progress?at={T0}", acc="TD-ACC-C2")
    if prog2["defect"]["value"] is not None or "산출 불가" not in (prog2["defect"]["note"] or ""):
        problems.append(f"매핑 없는 사업의 결함 {prog2['defect']}")
    summary2 = _get(target, s0, f"/api/projects/{pid2}/issues/summary", acc="TD-ACC-C2")["kinds"]
    if summary2["defectMapped"] or summary2["generalTotal"] != summary2["allTotal"] or summary2["defectRate"] is not None:
        problems.append(f"매핑 없는 사업의 종류별 건수 {summary2}")
    assert not problems, problems


def test_UC_041_S10_조회_실패(target, s0, screen):
    """한 카드의 집계만 실패 → 그 카드만 오류·재시도, 나머지 정상, 데이터 없음과 모양이 다르다 (AC-041-11).

    장애는 브라우저에서 그 위젯의 값 요청(/api/widgets/{id}/data)만 500 으로 바꿔 넣는다. 서버와 다른
    사용자에게는 영향이 없다. 재시도 전에 주입을 거둬 회복도 본다."""
    if not screen:
        pytest.skip("화면 시나리오. 원격 대상 + AXLINK_BROWSER_CHROME 에서 돈다")
    pid = s0.ids["TD-PRJ-3"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    board = next(b for b in _get(target, s0, f"/api/dashboards?projectId={pid}") if b["isDefault"])
    made: list[dict] = []
    try:
        for measure, title in (
            ("open_risk_count", "TST 정상 카드"),
            ("issue_resolution_rate", "TST 자료 없는 카드"),
            ("open_risk_count", "TST 장애 카드"),
        ):
            res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec(measure, [], [pid], "STAT_CARD", title)}, headers=c1)
            assert res.status_code == 201, res.text
            made.append(res.json())
        broken = f"/api/widgets/{made[2]['id']}/data"
        sc = screen("TD-ACC-C1").inject_error(broken)
        sc.open(f"/p/{pid}/dashboard")

        def card(title):
            return sc.page.locator("[data-slot=card]", has_text=title).first

        failed = "위젯을 불러오지 못했습니다"
        from playwright.sync_api import expect

        expect(card("TST 장애 카드")).to_contain_text(failed, timeout=15000)
        expect(card("TST 장애 카드")).to_contain_text("재시도")
        for title in ("TST 정상 카드", "TST 자료 없는 카드"):
            expect(card(title)).not_to_contain_text(failed)
        assert card("TST 자료 없는 카드").inner_text() != card("TST 장애 카드").inner_text()
        sc.shot("장애_주입")
        sc.clear_injection(broken)
        card("TST 장애 카드").get_by_role("button", name="재시도").click()
        expect(card("TST 장애 카드")).not_to_contain_text(failed, timeout=15000)
        sc.done()
    finally:
        for w in made:
            target.delete(f"/api/widgets/{w['id']}", headers=c1)


@pytest.mark.skip(reason="실모델이 필요하다. 온프레미스 모델 선정 뒤 5174 에서 본다")
def test_UC_041_S11_AI_와_일치(target, s0):
    """카드 값 vs AI 집계 답 (AC-041-2)."""


# ------------------------------------------------------------------ UC-042


FIVE_AXES = [
    ("STAT_CARD", "progress_representative_pct", []),
    ("STAT_CARD", "schedule_variance_pct", []),
    ("STAT_CARD", "issue_resolution_rate", []),
    ("BAR_CHART", "open_risk_count", ["risk_severity"]),
    ("STAT_CARD", "deliverable_approval_rate", []),
]


def test_UC_042_S01_추천_구성(target, s0, screen):
    """다섯 축 카드가 서버에 저장되고 값이 집계와 같으며 다른 세션에서도 같다 (AC-042-1·4)."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    boards = _get(target, s0, f"/api/dashboards?projectId={pid}")
    board = next(b for b in boards if b["isDefault"])
    made = []
    for n, (template, measure, dims) in enumerate(FIVE_AXES):
        # 화면처럼 자리(gridItem)를 같이 보낸다. 자리 없이 만든 위젯은 배치에 들지 않는다
        grid = {"i": "new", "x": (n % 3) * 4, "y": (n // 3) * 4, "w": 4, "h": 4}
        res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec(measure, dims, [pid], template, f"TST {measure}"), "gridItem": grid}, headers=c1)
        assert res.status_code == 201, (measure, res.text[:200])
        made.append(res.json())
    for w in made:
        data = target.post(f"/api/widgets/{w['id']}/data", json={}, headers=c1).json()
        assert data["measure"] == w["spec"]["query"]["measure"]
        if data["measure"] == "progress_representative_pct":
            assert round(_total(data) or 0, 4) in (0.3, 30.0), _total(data)
        if data["measure"] == "issue_resolution_rate":
            assert round(_total(data) or 0, 4) in (0.6667, 66.67, 66.7), _total(data)
    # 다른 세션(새 로그인)에서 같은 구성
    other = s0.login(d.ACCOUNTS["TD-ACC-C1"].username, PASSWORD)
    detail = target.get(f"/api/dashboards/{board['id']}", headers={"Authorization": f"Bearer {other}"}).json()
    assert {w["id"] for w in detail["widgets"]} >= {w["id"] for w in made}
    assert [g["i"] for g in detail["layout"]["lg"]] and len(detail["layout"]["lg"]) >= len(made)
    _ui_UC_042_S01(screen, target, s0, board["id"])


def test_UC_042_S05_기본_구성(target, s0, screen):
    """스냅샷 3일(산출물 대상 없는 날 하나) → 세 기준 일별 추이는 산출물 선만 그날 비우고, 카드는 마지막 점과
    같다. 화면: 편집 모드 「초기화」 → 기본 구성(세 기준 카드·일별 추이·진행 중인 WBS 작업), 위젯 수정 창에
    만든 근거, 「전체 삭제」 → 빈 화면 (AC-042-6)."""
    from app.db import tx

    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    days = (("2026-10-01", 40.0, (2, 10), (1, 4)), ("2026-10-02", 45.5, (3, 10), (2, 4)),
            ("2026-10-03", 50.0, (0, 0), (2, 4)))
    with tx() as cur:
        saved = cur.execute(
            "select * from progress_snapshot where project_id = %s", (pid,)
        ).fetchall()
        cur.execute("delete from progress_snapshot where project_id = %s", (pid,))
        for day, wbs, dl, req in days:
            cur.execute(
                """
                insert into progress_snapshot (project_id, snapshot_date, level, representative_pct,
                       wbs_actual_pct, deliverable_approved_count, deliverable_total_count,
                       requirement_verified_count, requirement_total_count)
                values (%s, %s, 'L1', %s, %s, %s, %s, %s, %s)
                """,
                (pid, day, wbs, wbs, *dl, *req),
            )
    boards = _get(target, s0, f"/api/dashboards?projectId={pid}")
    board = next(b for b in boards if b["isDefault"])
    before = {w["id"] for w in _get(target, s0, f"/api/dashboards/{board['id']}")["widgets"]}
    try:
        def preview(template: str, measure: str, dims: list[str], limit: int | None = None) -> dict:
            spec = _spec(measure, dims, [pid], template, "TST 기본 구성")
            spec["query"]["limit"] = limit
            res = target.post("/api/widgets/preview", json={"spec": spec}, headers=c1)
            assert res.status_code == 200, res.text[:200]
            return res.json()

        line = preview("LINE_CHART", "progress_metric_pct", ["period_day", "progress_metric"], 400)
        got = {(r["values"]["d0"], r["values"]["d1"]): float(r["values"]["value"]) for r in line["rows"]}
        assert got[("2026-10-01", "산출물 승인률")] == 20.0 and got[("2026-10-02", "산출물 승인률")] == 30.0
        assert ("2026-10-03", "산출물 승인률") not in got, "산출물 대상이 없는 날을 0 으로 그렸다"
        assert got[("2026-10-03", "WBS 진척률")] == 50.0 and got[("2026-10-03", "요구사항 이행률")] == 50.0

        def card(measure: str) -> float:
            b = preview("STAT_CARD", measure, [])
            row = b["rows"][0] if b["rows"] else b["total"]
            return float(row["values"]["value"])

        assert card("progress_wbs_pct") == got[("2026-10-03", "WBS 진척률")]
        assert card("snapshot_requirement_fulfillment_pct") == got[("2026-10-03", "요구사항 이행률")]
        assert card("snapshot_work_product_approval_pct") == got[("2026-10-02", "산출물 승인률")]
        _ui_UC_042_S05(screen, target, s0, board["id"])
    finally:
        with tx() as cur:
            cur.execute("delete from progress_snapshot where project_id = %s", (pid,))
            for r in saved:
                cols = list(r.keys())
                cur.execute(
                    f"insert into progress_snapshot ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                    [r[c] for c in cols],
                )
        # 화면 단계가 위젯을 바꿨으면 시험 전 구성은 되살리지 못한다. 다음 시험은 기본 구성 위에서 돈다
        _ = before


def _ui_UC_042_S05(screen, target, s0, board_id: str):
    """화면: 편집 모드 → 초기화 → 기본 구성 위젯(세 기준 카드·일별 추이·진행 중인 WBS 작업) → WBS 진척률 위젯
    수정 창의 「만든 근거」 → 전체 삭제 → 빈 화면 → 기본 구성 놓기."""
    if not screen:
        return
    from playwright.sync_api import expect

    pid = s0.ids["TD-PRJ-1"]
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/dashboard").see("대시보드")
    sc.page.get_by_role("button", name="편집 모드").first.click()
    sc.page.get_by_role("button", name="초기화").click()
    confirm = sc.page.get_by_role("alertdialog")
    expect(confirm).to_contain_text("기본 구성으로 초기화할까요?")
    confirm.get_by_role("button", name="초기화").click()
    expect(confirm).to_be_hidden(timeout=60000)
    sc.see("WBS 진척률", "산출물 승인률", "요구사항 이행률", "일별 진척률", "진행 중인 WBS 작업", selector="main", timeout=60000)
    titles = [w["spec"]["title"] for w in _get(target, s0, f"/api/dashboards/{board_id}")["widgets"]]
    assert {"WBS 진척률", "산출물 승인률", "요구사항 이행률", "진행 중인 WBS 작업"} <= set(titles), titles
    sc.shot("기본 구성")

    card = sc.page.locator(".react-grid-item", has_text="WBS 진척률").first
    card.get_by_role("button", name="위젯 수정").click()
    sc.see("만든 근거", "일정 기준 진척", selector='[role="dialog"]')
    sc.shot("위젯 수정 창 근거")
    sc.page.keyboard.press("Escape")

    sc.page.get_by_role("button", name="전체 삭제").click()
    confirm = sc.page.get_by_role("alertdialog")
    expect(confirm).to_contain_text("위젯을 모두 지울까요?")
    confirm.get_by_role("button", name="전체 삭제").click()
    expect(confirm).to_be_hidden(timeout=60000)
    sc.page.get_by_role("button", name="편집 모드 닫기").click()
    sc.see("위젯이 없습니다", selector="main")
    assert _get(target, s0, f"/api/dashboards/{board_id}")["widgets"] == []
    sc.shot("전체 삭제 뒤 빈 화면")
    sc.done()


def test_UC_042_S02_없는_짝(target, s0):
    """지표 「없는키」 저장 → 거절 (AC-042-2)."""
    pid = s0.ids["TD-PRJ-1"]
    boards = _get(target, s0, f"/api/dashboards?projectId={pid}")
    board = next(b for b in boards if b["isDefault"])
    res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec("없는키", [], [pid])}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 400, res.text
    res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec("open_risk_count", ["없는차원"], [pid])}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 400, res.text


@pytest.mark.skipif(
    not TARGET_URL,
    reason="가짜 모델은 자연어를 명세로 바꾸지 못한다(NOT_EXPRESSIBLE). 원격 대상(5174 실모델)에서 본다",
)
def test_UC_042_S03_자연어_위젯(target, s0):
    """「심각도별 열린 리스크 막대」 → open_risk_count·risk_severity·BAR_CHART 선택, 값은 집계 (AC-042-3)."""
    pid = s0.ids["TD-PRJ-1"]
    res = target.post("/api/widgets/generate", json={"prompt": "심각도별 열린 리스크 막대", "projectScope": [pid]}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text
    body = res.json()
    spec = body.get("spec") or (body.get("widget") or {}).get("spec")
    assert spec, body
    assert spec["query"]["measure"] == "open_risk_count", spec["query"]
    assert spec["query"]["dimensions"] == ["risk_severity"], spec["query"]
    assert spec["template"] == "BAR_CHART", spec["template"]
    data = target.post("/api/widgets/preview", json={"spec": spec}, headers=auth(s0.tokens["TD-ACC-C1"])).json()
    assert sum(r["values"]["value"] for r in data["rows"]) == 1


def test_UC_042_S04_용역사(target, s0):
    """V1 편집 거절, 보기 가능 (AC-042-5)."""
    pid = s0.ids["TD-PRJ-1"]
    boards = _get(target, s0, f"/api/dashboards?projectId={pid}", acc="TD-ACC-V1")
    board = next(b for b in boards if b["isDefault"])
    assert board["editable"] is False
    res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec("open_risk_count", [], [pid])}, headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code == 403, res.text
    assert target.get(f"/api/dashboards/{board['id']}", headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 200


# ------------------------------------------------------------------ UC-043


def test_UC_043_S01_목록_원천(target, s0, screen):
    """일반 이슈 9, 열림 3, 해결 6(66.7%). 각 행 원천(도구·연결·번호)·링크 (AC-043-1·4)."""
    pid = s0.ids["TD-PRJ-1"]
    summary = _get(target, s0, f"/api/projects/{pid}/issues/summary")
    rows = _get(target, s0, f"/api/projects/{pid}/issues?size=100")["content"]
    problems: list[str] = []
    if summary["total"] != 9 or summary["open"] != 3 or summary["closed"] != 6:
        problems.append(f"요약 전체 {summary['total']}·열림 {summary['open']}·해결 {summary['closed']} (기대 9·3·6)")
    kinds = summary.get("kinds") or {}
    if (kinds.get("allTotal"), kinds.get("generalTotal"), kinds.get("defectTotal")) != (11, 9, 2):
        problems.append(f"종류별 건수 {kinds} (기대 전체 11·일반 9·결함 2, DEC-02)")
    if any(r.get("kind") != "GENERAL" for r in rows):
        problems.append("일반 이슈 목록에 결함이 섞였다")
    if len(rows) != summary["total"]:
        problems.append(f"목록 {len(rows)} ≠ 요약 {summary['total']}")
    for r in rows:
        src = r["source"]
        if not (src.get("tool") and src.get("connectionName") and (src.get("number") or src.get("externalId")) and src.get("externalUrl")):
            problems.append(f"원천 표기 부족: {r['key']} {src}")
            break
    assert not problems, problems
    _ui_UC_043_S01(screen, target, s0, summary, rows)


def test_UC_043_S02_트래커_버전(target, s0):
    """TD-ISS-R3: 트래커 일감, 버전 2차(기한 08-31), 커스텀 필드 UR.PORT.002, 요구사항 B 연결 (AC-043-2)."""
    pid = s0.ids["TD-PRJ-1"]
    rows = {r["key"]: r for r in _get(target, s0, f"/api/projects/{pid}/issues?size=100")["content"]}
    r3 = rows["RM-203"]
    problems: list[str] = []
    if not r3.get("milestone") or r3["milestone"]["title"] != "2차" or r3["milestone"]["dueOn"] != "2026-08-31":
        problems.append(f"버전 {r3.get('milestone')}")
    if "일감" not in str(r3):
        problems.append("트래커 「일감」이 보이지 않는다")
    if "UR.PORT.002" not in str(r3):
        problems.append("커스텀 필드 UR.PORT.002 가 보이지 않는다")
    detail_b = _get(target, s0, f"/api/projects/{pid}/requirements/{s0.ids['TD-REQ-B']}")
    if not any("203" in str(lk.get("fromLabel")) or "민원 조회 화면" in str(lk.get("fromLabel")) for lk in detail_b["traceLinks"]):
        problems.append("R3 → B 연결이 요구사항 상세에 없다")
    assert not problems, problems


def test_UC_043_S03_번호_겹침(target, s0):
    """G4·W4 두 행, TD-CON-1 필터 2건(G4·G5)·TD-CON-3 필터 1건 (AC-043-3)."""
    pid = s0.ids["TD-PRJ-1"]
    con1 = _get(target, s0, f"/api/projects/{pid}/issues?size=100&connectionId={s0.ids['TD-CON-1']}")
    con3 = _get(target, s0, f"/api/projects/{pid}/issues?size=100&connectionId={s0.ids['TD-CON-3']}")
    summary = _get(target, s0, f"/api/projects/{pid}/issues/summary")
    problems: list[str] = []
    if {r["key"] for r in con1["content"]} != {"GH-4", "GH-5"}:
        problems.append(f"TD-CON-1 필터 {[r['key'] for r in con1['content']]}")
    if [r["key"] for r in con3["content"]] != ["GH-4"]:
        problems.append(f"TD-CON-3 필터 {[r['key'] for r in con3['content']]}")
    by_con = {s["connectionId"]: s["count"] for s in summary["sources"]} if summary.get("sources") else {}
    if by_con and (by_con.get(s0.ids["TD-CON-1"]) != 2 or by_con.get(s0.ids["TD-CON-3"]) != 1):
        problems.append(f"요약 카드 연결별 건수 {by_con}")
    # 같은 번호 #4 가 연결마다 한 행씩, 두 행으로 보여야 한다
    all_rows = _get(target, s0, f"/api/projects/{pid}/issues?size=100")["content"]
    if sum(1 for r in all_rows if r["key"] == "GH-4") != 2:
        problems.append(f"#4 행 수 {sum(1 for r in all_rows if r['key'] == 'GH-4')} (기대 2)")
    assert not problems, problems


def test_UC_043_S04_심각도_미지정(target, s0):
    """수집 이슈 심각도 미지정으로, 고위험 0 (AC-043-5)."""
    summary = _get(target, s0, f"/api/projects/{s0.ids['TD-PRJ-1']}/issues/summary")
    assert summary["heavyOpen"] == 0, summary
    assert summary["unspecifiedOpen"] == summary["open"], summary


def test_UC_043_S05_리스크_결함(target, s0):
    """리스크 2(열림 1 높음), 위험 처리율 50.0%. 결함 목록 2건(R9·R10)·결함 처리율 50.0% (AC-043-6, DEC-02).

    리스크 목록 화면 API 는 따로 없어 리스크 쪽은 집계(시맨틱)로 본다."""
    pid = s0.ids["TD-PRJ-1"]
    problems: list[str] = []
    risks = _preview(target, s0, "open_risk_count", ["risk_severity"], template="BAR_CHART")
    sev = {r["values"]["d0"]: r["values"]["value"] for r in risks["rows"]}
    if sev.get("HIGH", 0) + sev.get("CRITICAL", 0) != 1 or sum(sev.values()) != 1:
        problems.append(f"열린 리스크 {sev}")
    if round(_total(_preview(target, s0, "risk_resolution_rate", [])) or 0, 4) not in (0.5, 50.0):
        problems.append("위험 처리율")
    defects = _get(target, s0, f"/api/projects/{pid}/issues?size=100&kind=DEFECT")["content"]
    if sorted(r["key"] for r in defects) != ["RM-209", "RM-210"] or any(r["kind"] != "DEFECT" for r in defects):
        problems.append(f"결함 목록 {[(r['key'], r['kind']) for r in defects]}")
    summary = _get(target, s0, f"/api/projects/{pid}/issues/summary?kind=DEFECT")
    kinds = summary["kinds"]
    if (summary["total"], summary["open"], summary["closed"]) != (2, 1, 1):
        problems.append(f"결함 요약 {summary['total']}·{summary['open']}·{summary['closed']}")
    if not kinds["defectMapped"] or kinds["defectRate"] != 0.5:
        problems.append(f"결함 처리율 {kinds}")
    all_rows = _get(target, s0, f"/api/projects/{pid}/issues?size=100&kind=ALL")["totalElements"]
    if all_rows != kinds["allTotal"] or all_rows != 11:
        problems.append(f"전체 이슈(결함 포함) 목록 {all_rows}")
    assert not problems, problems


def test_UC_043_S06_다른_사업_연결_필터(target, s0):
    """V3 의 TD-CON-4 ID 로 PRJ-1 필터 → 0건 (AC-043-7)."""
    res = target.get(f"/api/projects/{s0.ids['TD-PRJ-1']}/issues?size=100&connectionId={s0.ids['TD-CON-4']}", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code in (200, 400, 404), res.text
    if res.status_code == 200:
        assert res.json()["totalElements"] == 0, res.json()["totalElements"]


def test_UC_043_S07_출처_이슈_제외(target, s0):
    """G1~G3 은 일반 이슈 9 에 포함되지 않고 산출 근거 문장에 명시 (A2)."""
    pid = s0.ids["TD-PRJ-1"]
    keys = {r["key"] for r in _get(target, s0, f"/api/projects/{pid}/issues?size=100")["content"]}
    assert not {"GH-1", "GH-2"} & keys, keys
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")
    assert "요구사항" in (prog["issue"].get("note") or ""), prog["issue"]


# ------------------------------------------------------------------ 스냅샷 추이 (S0r → S0a → S1)


def test_UC_041_S06_스냅샷_추이(target, s0):
    """S1: 09-25 행 30.0/72.9 → 09-26 행 39.0/73.4. 전일 대비 +9.0%p·+0.5%p (AC-041-8, IM-005A 7.1)."""
    s0.s0a()
    s0.s1()
    rows = {r["snapshotDate"]: r for r in _get(target, s0, f"/api/projects/{s0.ids['TD-PRJ-1']}/snapshots?limit=366")}
    assert "2026-09-25" in rows and "2026-09-26" in rows, sorted(rows)[-5:]
    a, b = rows["2026-09-25"], rows["2026-09-26"]
    # 스냅샷은 백분율(%)로 저장된다. 문서 표시값과 비교한다
    assert round(a["representativePct"], 1) == 30.0 and round(a["wbsPlannedPct"], 2) == 72.85, a
    assert round(b["representativePct"], 1) == 39.0 and round(b["wbsPlannedPct"], 2) == 73.44, b
    assert round(b["representativePct"] - a["representativePct"], 1) == 9.0
    assert round(b["wbsPlannedPct"] - a["wbsPlannedPct"], 2) == 0.59
    t0 = rows["2026-09-15"]
    assert round(t0["representativePct"], 1) == 30.0 and round(t0["wbsPlannedPct"], 2) == 66.95, t0


def _ui_UC_040_S01(screen, s0):
    """화면: 발주기관 목록 3건, PRJ-1 진척 30.0%·편차·요청 1·리스크 1, PRJ-3 비율 없음·요청 없음."""
    if not screen:
        return
    sc = screen("TD-ACC-C1")
    sc.open("/projects").see("총 3건")
    sc.not_see(d.PROJECTS["TD-PRJ-2"].name)
    p1 = sc.row(d.PROJECTS["TD-PRJ-1"].name)
    for want in ("30.0%", "%p", "요청 1", "리스크 1"):
        assert want in p1, f"PRJ-1 줄에 {want} 가 없다: {p1!r}"
    p3 = sc.row(d.PROJECTS["TD-PRJ-3"].name)
    assert "%" not in p3 and "요청" not in p3, p3
    sc.done()
    sc = screen("TD-ACC-V1")
    sc.open("/projects").see("총 2건", d.PROJECTS["TD-PRJ-1"].name, d.PROJECTS["TD-PRJ-9"].name)
    sc.done()


def _ui_UC_041_S04(screen, s0):
    """화면: TD-PRJ-3 일정 고지문·「산출 불가」, 스냅샷을 기록하면 「산정 불가」."""
    if not screen:
        return
    pid = s0.ids["TD-PRJ-3"]
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/schedule").see("진척률 산정의 핵심 입력이 빠져 있습니다", "산출 불가")
    sc.not_see(re.compile(r"(?<![\d.])0(\.0)?%"))
    sc.shot("일정")
    res = s0.c.post(f"/api/projects/{pid}/snapshots", headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text
    sc.open(f"/p/{pid}/snapshots").see("산정 불가")
    sc.not_see(re.compile(r"(?<![\d.])0(\.0)?%"))
    sc.done()


# ------------------------------------------------------------------ 화면 값 맞추기
# 화면의 숫자는 화면이 받은 API 값을 프런트가 그대로 적은 것이어야 한다. 아래는 프런트의 표기
# 규칙(frontend/src/features/widgets/widget-data.ts·renderers.tsx, lib/format.ts)을 옮긴 것이다.
# 일정·위젯 화면은 서버의 오늘로 센다. 계획선·편차처럼 날짜에 따라 바뀌는 값은 IM-005A 의 T0 값이
# 아니라 같은 화면이 부르는 API(기준일 없이)의 값과 비교한다.

_NUMERIC = {"number", "percent", "COUNT", "RATE_PCT", "DAYS", "PCT_POINT"}
_DELIVERABLE_WORD = {"SUBMITTED": "제출", "MISSING": "미제출", "OVERDUE": "지연", "NONE": ""}
_COMPLETION_WORD = {"CONFIRMED": "완료 확인됨", "RECONFIRM": "재확인 필요(범위 변경)", "WITHDRAWN": "확인 철회됨", "NONE": "완료 확인 없음"}
_TOOL_NAME = {"GITHUB": "GitHub", "REDMINE": "Redmine", "UPLOAD": "업로드", "MANUAL": "수기"}
_ISSUE_STATUS = {"OPEN": "열림", "IN_PROGRESS": "진행중", "RESOLVED": "해결", "CLOSED": "종료"}  # lib/labels.ts


def _js_number(v) -> str:
    """JS `n.toLocaleString('ko-KR')`: 소수 셋째 자리까지(반올림), 천 단위 쉼표."""
    from decimal import ROUND_HALF_UP, Decimal

    q = Decimal(str(v)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    text = f"{q:,f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _js_round(x: float) -> int:
    """JS Math.round (0.5 는 올린다)."""
    import math

    return math.floor(x + 0.5)


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _stat_text(data: dict) -> str:
    """STAT_CARD 의 큰 숫자 칸(값 + 단위). 자료가 없으면 그 문구 (widget-host.tsx·StatCardWidget)."""
    if not data["rows"] and data.get("total") is None:
        return "조건에 맞는 데이터가 없습니다."
    col = next((c for c in data["columns"] if c.get("type") in _NUMERIC), None)
    if col is None:
        return "-"

    def at(row):
        raw = ((row or {}).get("values") or {}).get(col["key"])
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int | float):
            return raw
        try:
            return float(raw) if isinstance(raw, str) and raw.strip() else None
        except ValueError:
            return None

    value = at(data.get("total"))
    if value is None:
        value = at(data["rows"][0] if data["rows"] else None)
    if value is None:
        return "-"
    return _js_number(value) + (data.get("unit") or "")


def _cell_text(value) -> str:
    """widget-data.ts formatCell."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, int | float):
        return _js_number(value)
    return str(value)


def _card(sc, title: str):
    """제목이 꼭 그것인 위젯 카드(「요구사항 이행률」과 「월별 요구사항 이행률 추이」를 가른다)."""
    exact = sc.page.locator("[data-slot=card-title]", has_text=re.compile(rf"^\s*{re.escape(title)}\s*$"))
    return sc.page.locator(".react-grid-layout [data-slot=card]").filter(has=exact).first


def _check_widget_cards(sc, target, c1: dict, widgets: list[dict]) -> None:
    """위젯 카드마다: 오류 없음, STAT_CARD 숫자 = 위젯 값 API, DATA_TABLE 줄 = API 행, 산출 근거 문장 = API."""
    from playwright.sync_api import expect

    for w in widgets:
        spec = w["spec"]
        res = target.post(f"/api/widgets/{w['id']}/data", json={}, headers=c1)
        assert res.status_code == 200, (spec["title"], res.text[:200])
        data = res.json()
        card = _card(sc, spec["title"])
        # 카드 설명 줄(지표 이름 · 프로젝트 n개)은 값을 받은 뒤에 찬다
        expect(card).to_contain_text(data["measureLabel"], timeout=20000)
        expect(card).not_to_contain_text("위젯을 불러오지 못했습니다")
        if spec["template"] == "STAT_CARD":
            want = _stat_text(data)
            got = _flat(card.inner_text())
            assert _flat(want) in got, f"{spec['title']}: 화면 {got!r} / API {want!r}"
        elif spec["template"] == "DATA_TABLE":
            labelled = {c["key"] for c in data["columns"] if any(o["key"] == f"{c['key']}_label" for o in data["columns"])}
            keys = [c["key"] for c in data["columns"] if c["key"] not in labelled]
            for row in data["rows"]:
                cells = [_cell_text((row.get("values") or {}).get(k)) for k in keys]
                line = card.locator("tbody tr", has_text=cells[0]).first
                for cell in cells:
                    expect(line).to_contain_text(cell)
        if data.get("basis"):
            card.get_by_role("button", name="산출 근거").click()
            expect(card.get_by_test_id("widget-basis")).to_have_text(data["basis"].strip())


def _ui_UC_041_S01(screen, target, s0):
    """화면: 다섯 축(진척·일정·품질·리스크·산출물) 카드를 사업 대시보드 한 화면에 놓고, 카드 숫자 =
    위젯 값 API, 카드마다 산출 근거 문장 = API (AC-041-1·3).

    시험이 카드를 API 로 놓고(화면이 쓰는 것과 같은 위젯 명세) 끝나면 지운다. 진척 30.0%·일반 이슈
    처리율 66.7% 처럼 날짜와 무관한 값은 위 API 단언이 IM-005A 와 이미 맞췄다."""
    if not screen:
        return
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    board = next(b for b in _get(target, s0, f"/api/dashboards?projectId={pid}") if b["isDefault"])
    axes = [  # (축, 지표, 차원, 템플릿)
        ("진척", "progress_representative_pct", [], "STAT_CARD"),
        ("진척", "schedule_variance_pct", [], "STAT_CARD"),
        ("일정", "schedule_compliance_rate", [], "STAT_CARD"),
        ("품질", "issue_resolution_rate", [], "STAT_CARD"),
        ("품질", "defect_resolution_rate", [], "STAT_CARD"),
        ("품질", "risk_resolution_rate", [], "STAT_CARD"),
        ("품질", "requirement_fulfillment_rate", [], "STAT_CARD"),
        ("리스크", "open_risk_count", ["risk_severity"], "DATA_TABLE"),
        ("산출물", "deliverable_approval_rate", [], "STAT_CARD"),
    ]
    made: list[dict] = []
    try:
        for n, (axis, measure, dims, template) in enumerate(axes):
            grid = {"i": "new", "x": (n % 3) * 4, "y": (n // 3) * 4, "w": 4, "h": 4}
            spec = _spec(measure, dims, [pid], template, f"TST {axis} {measure}")
            res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": spec, "gridItem": grid}, headers=c1)
            assert res.status_code == 201, (measure, res.text[:200])
            made.append(res.json())
        sc = screen("TD-ACC-C1")
        sc.open(f"/p/{pid}/dashboard").see("대시보드")
        _check_widget_cards(sc, target, c1, made)
        # 다섯 축이 한 화면(같은 대시보드)에 다 있다
        for w in made:
            assert _card(sc, w["spec"]["title"]).is_visible(), w["spec"]["title"]
        sc.done()
    finally:
        for w in made:
            target.delete(f"/api/widgets/{w['id']}", headers=c1)


def _ui_UC_041_S02(screen, target, s0):
    """화면: 일정(WBS)에서 작업 단위로 계획·실적·산출물 판정·격차 경고·연결 이슈와 그 상태, 완료 확인
    상태 (AC-041-4). 값은 화면과 같은 API(기준일 없이 = 서버의 오늘)에서 받는다."""
    if not screen:
        return
    from playwright.sync_api import expect

    pid = s0.ids["TD-PRJ-1"]
    wbs = _get(target, s0, f"/api/projects/{pid}/wbs")
    comp = _get(target, s0, f"/api/projects/{pid}/wbs/completion")
    by = {i["wbsId"]: i for i in wbs["items"]}
    citems = {i["wbsId"]: i for i in comp["items"]}
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/schedule").see("일정(WBS)", "보고 진척률", "완료 확인율", "작업 일정")

    # 보고 진척률·완료 확인율 카드와 작업별 완료 확인 (completion-panel.tsx)
    panel = sc.page.locator('section[aria-label="작업 완료 확인"]')
    reported = "산출 불가" if comp["reportedPct"] is None else f"{comp['reportedPct'] * 100:.1f}%"
    rate = "산출 불가" if comp["completionRate"] is None else f"{_js_number(_js_round(comp['completionRate'] * 1000) / 10)}%"
    expect(panel).to_contain_text(reported)
    expect(panel).to_contain_text(rate)
    sc.page.get_by_role("tab", name="WBS").click()
    for wid in ("3.1", "3.2"):
        ci = citems[wid]
        word = _COMPLETION_WORD[ci["completionStatus"]]
        if ci["completionStatus"] == "NONE" and ci.get("predecessorConfirmed"):
            word = "재확인 필요"
        row = sc.page.locator("tr").filter(has_text=ci["name"]).filter(has_text=wid).first
        expect(row).to_contain_text(word)
    sc.shot("완료_확인")

    # 작업 일정 머리줄: 계획보다 늦은 작업 수, 산출물 대조 (schedule-page.tsx)
    leaves = [i for i in wbs["items"] if i["level"] > 0 or len(wbs["items"]) == 1]
    late = sum(1 for i in leaves if i["progress"] < 100 and i["progress"] < i["planned"])
    head = _flat(sc.text("main"))
    assert (f"계획보다늦은작업{late}개" if late else "모두계획대로진행중") in head, head[:400]
    dl = wbs.get("deliverables") or {}
    expected = dl.get("submitted", 0) + dl.get("missing", 0) + dl.get("overdue", 0)
    if expected:
        assert f"산출물파일대조{dl['submitted']}/{expected}개" in head, head[:400]
    # 경고는 「격차 경고 n건」(또는 「확인할 점 n건」) 버튼을 눌러 연다(11-18)
    if wbs["warnings"]:
        sc.page.get_by_test_id("schedule-warnings").click()
        for w in wbs["warnings"]:
            sc.see(w.removeprefix("격차 경고: "))
        sc.page.keyboard.press("Escape")

    # WBS 표: 3.2 지연(40%), 계획선, 산출물 판정. 격차 경고는 API 가 붙인 줄에만 (DEC-20 (b))
    sc.page.get_by_role("tab", name="WBS").click()
    table = sc.page.get_by_role("tabpanel")
    for wid in ("3.2", "3.3"):
        item = by[wid]
        row = table.locator("tbody tr").filter(has_text=item["name"]).first
        expect(row).to_contain_text(f"{item['planned']}%")
        expect(row).to_contain_text(f"{item['progress']}%")
        word = _DELIVERABLE_WORD.get(item.get("deliverableStatus") or "NONE", "")
        if word:
            expect(row).to_contain_text(word)
        if item.get("gapWarning"):
            expect(row).to_contain_text("격차 경고")
        else:
            expect(row).not_to_contain_text("격차 경고")
        # 연결 이슈 칸: 이슈 번호(원문 링크)와 상태를 이슈 화면과 같은 말로
        for li in item.get("linkedIssues") or []:
            expect(row).to_contain_text(li["key"] or li["title"])
            expect(row).to_contain_text(_ISSUE_STATUS.get(li["status"], li["status"]))
            if li.get("url"):
                expect(row.locator(f'a[href="{li["url"]}"]')).to_have_count(1)
    linked = by["3.2"].get("linkedIssues") or []
    assert any("204" in (li["key"] or "") for li in linked), f"3.2 의 연결 이슈 {linked}"
    if not any(i.get("gapWarning") for i in wbs["items"]):
        sc.not_see("격차 경고")
    sc.done()


def _ui_UC_042_S01(screen, target, s0, board_id: str):
    """화면: 편집 모드 → 추천 구성 「전체 진행 현황」 → 바꾸기. 다섯 축 카드가 생기고 숫자 = 위젯 값
    API, 레이아웃은 서버에 저장돼 새 브라우저 문맥(화면으로 다시 로그인)에서도 자리가 같다. 브라우저
    저장소에는 위젯·배치가 없다 (AC-042-1·4)."""
    if not screen:
        return
    from playwright.sync_api import expect

    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/dashboard").see("대시보드")
    sc.page.get_by_role("button", name="편집 모드").first.click()
    sc.page.get_by_role("button", name="추천 구성").click()
    sc.page.get_by_role("dialog").locator("button", has_text="전체 진행 현황").click()
    confirm = sc.page.get_by_role("alertdialog")
    expect(confirm).to_contain_text("이 구성으로 바꿀까요?")
    confirm.get_by_role("button", name="바꾸기").click()
    expect(confirm).to_be_hidden(timeout=60000)
    sc.page.get_by_role("button", name="편집 모드 닫기").click()

    detail = _get(target, s0, f"/api/dashboards/{board_id}")
    widgets = detail["widgets"]
    measures = {w["spec"]["query"]["measure"] for w in widgets}
    axes = {
        "진척": {"progress_representative_pct"},
        "일정": {"schedule_variance_pct", "schedule_compliance_rate"},
        "품질": {"issue_resolution_rate", "requirement_fulfillment_rate", "defect_resolution_rate", "risk_resolution_rate"},
        "리스크": {"open_risk_count"},
        "산출물": {"deliverable_approval_rate"},
    }
    missing = [axis for axis, ms in axes.items() if not ms & measures]
    assert not missing, f"추천 구성에 빠진 축: {missing} (지표 {sorted(measures)})"
    placed = {g["i"] for g in detail["layout"]["lg"]}
    assert {w["id"] for w in widgets} <= placed, "레이아웃에 자리가 없는 위젯이 있다"

    sc.open(f"/p/{pid}/dashboard").see("대시보드")
    expect(sc.page.locator(".react-grid-layout [data-slot=card]")).to_have_count(len(widgets), timeout=20000)
    _check_widget_cards(sc, target, c1, [w for w in widgets if w["spec"]["template"] == "STAT_CARD"])
    sc.shot("추천_구성")

    def boxes(screen_) -> dict[str, tuple[int, ...]]:
        out = {}
        for w in widgets:
            box = _card(screen_, w["spec"]["title"]).bounding_box()
            assert box, w["spec"]["title"]
            out[w["spec"]["title"]] = tuple(round(box[k]) for k in ("x", "y", "width", "height"))
        return out

    def stored(screen_) -> str:
        return screen_.page.evaluate("() => JSON.stringify(Object.assign({}, window.localStorage))")

    sc.page.evaluate("() => document.querySelector('main')?.scrollTo(0, 0)")
    first = boxes(sc)
    assert not any(w["id"] in stored(sc) for w in widgets), "브라우저 저장소에 위젯 id 가 있다"
    sc.done()

    # 다른 브라우저: 새 문맥에서 화면으로 다시 로그인해 같은 대시보드를 연다
    other = screen("TD-ACC-C1", fresh_password=PASSWORD)
    other.open(f"/p/{pid}/dashboard").see("대시보드")
    expect(other.page.locator(".react-grid-layout [data-slot=card]")).to_have_count(len(widgets), timeout=20000)
    for w in widgets:
        expect(_card(other, w["spec"]["title"])).not_to_contain_text("위젯을 불러오지 못했습니다")
    other.page.evaluate("() => document.querySelector('main')?.scrollTo(0, 0)")
    second = boxes(other)
    assert second == first, {t: (first[t], second.get(t)) for t in first if first[t] != second.get(t)}
    assert not any(w["id"] in stored(other) for w in widgets), "브라우저 저장소에 위젯 id 가 있다"
    other.done()


def _ui_UC_043_S01(screen, target, s0, summary: dict, rows: list[dict]):
    """화면: 수집한 이슈 전체(결함 포함)의 요약 카드와, 행마다 원천(도구 · 연결 · 저장소/프로젝트
    #번호 → 원문 링크) (AC-043-1·4, ARC-031). 종류·심각도는 화면에서 뺐다(2026-11-18). 일반·결함
    구분(DEC-02)은 API 와 결함 처리율 지표로 본다(UC-043-S05)."""
    if not screen:
        return
    from playwright.sync_api import expect

    pid = s0.ids["TD-PRJ-1"]
    summary = _get(target, s0, f"/api/projects/{pid}/issues/summary?kind=ALL")
    rows = _get(target, s0, f"/api/projects/{pid}/issues?size=100&kind=ALL")["content"]
    sc = screen("TD-ACC-C1")
    sc.open(f"/p/{pid}/issues").see("이슈")
    sc.not_see("심각도", "일반 이슈(결함 제외)")

    # 요약 카드: 열린 이슈 n (이슈 N건 중), 해결·닫힘 m (비율) (issues-page.tsx MetricCard)
    opened = sc.page.locator("[data-slot=card]", has_text="열린 이슈").first
    expect(opened).to_contain_text(f"이슈 {summary['total']}건 중")
    assert _flat(opened.inner_text()).startswith(f"열린이슈{summary['open']}"), opened.inner_text()
    closed = sc.page.locator("[data-slot=card]", has_text="해결·닫힘").first
    share = f"{_js_round(summary['closed'] / summary['total'] * 100)}%" if summary["total"] else "0%"
    assert _flat(closed.inner_text()) == f"해결·닫힘{summary['closed']}{share}", closed.inner_text()

    expect(sc.page.locator("tbody tr")).to_have_count(len(rows), timeout=20000)
    for r in rows:
        src = r["source"]
        number = f"{src['target']} #{src['number']}" if src.get("target") else f"#{src['number']}"
        href = f'a[href="{src["externalUrl"]}"]'
        link = sc.page.locator(f"tbody {href}").first
        expect(link).to_contain_text(number)
        assert str(src["number"]) in (link.get_attribute("href") or ""), src
        # has= 는 행 안에서 찾는다. 「tbody a」로 주면 행 안에 tbody 가 없어 아무 행도 맞지 않는다
        line = sc.page.locator("tbody tr", has=sc.page.locator(href)).first
        for text in (r["key"], _TOOL_NAME.get(src["tool"], src["tool"]), src["connectionName"]):
            expect(line).to_contain_text(text)
    sc.shot("이슈")
    sc.done()
