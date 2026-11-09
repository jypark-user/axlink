# ruff: noqa: E501
"""E 그룹: 현황 조회 (UC-040 ~ UC-043) 예제 시나리오.

S0 에서 시작해 UC-040-S01 이 S0r(TD-RR-1 등록)을 만들고, 다섯 축·일정 줄·이슈 조회를 T0 기준으로
본다. 스냅샷 추이(UC-041-S06)는 S0a → S1 전이가 필요해 맨 뒤에 돈다. DEC-01·02·17 과
브라우저·실모델 시나리오는 보류한다. 값은 IM-009 7 절의 독립 계산값과 비교한다.
"""

from __future__ import annotations

import pytest

from tests.fixtures.im009 import data as d
from tests.fixtures.im009.replay import Faults, ReplaySource, install, tool_base
from tests.scenarios.conftest import auth

pytestmark = pytest.mark.db

T0 = d.T0.isoformat()


@pytest.fixture
def replay(monkeypatch, s0) -> ReplaySource:
    return install(monkeypatch, ReplaySource(state="S0", files=s0.files))


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


def test_UC_040_S01_세_사업_목록(target, s0):
    """S0r: PRJ-1 진척 30.0%·편차 −36.9%p·미처리 1·리스크 1·승인 1/22. PRJ-3 지표 「—」·미처리 0 (AC-040-1·2·3·4)."""
    s0.s0r()
    rows = {p["id"]: p for p in _get(target, s0, "/api/projects?size=100")["content"]}
    p1, p3, p9 = rows[s0.ids["TD-PRJ-1"]], rows[s0.ids["TD-PRJ-3"]], rows[s0.ids["TD-PRJ-9"]]
    assert s0.ids["TD-PRJ-2"] not in rows  # C1 은 자기 조직 사업만
    problems: list[str] = []
    if p1["openReviewRequestCount"] != 1:
        problems.append(f"미처리 요청 {p1['openReviewRequestCount']} (기대 1)")
    if p1["openRiskCount"] != 1:
        problems.append(f"열린 리스크 {p1['openRiskCount']} (기대 1)")
    if (p1["requiredWorkProductApproved"], p1["requiredWorkProductTotal"]) != (1, 22):
        problems.append(f"승인 {p1['requiredWorkProductApproved']}/{p1['requiredWorkProductTotal']} (기대 1/22)")
    rep_key = next((k for k in p1 if "progress" in k.lower() or "representative" in k.lower()), None)
    if rep_key is None:
        problems.append(f"목록에 대표 진척률·편차 칸이 없다: {sorted(p1)}")
    elif round((p1[rep_key] or 0) * 100, 1) != 30.0:
        problems.append(f"대표 진척률 {p1[rep_key]} (기대 0.3000)")
    if p3["openReviewRequestCount"] != 0:
        problems.append(f"PRJ-3 미처리 {p3['openReviewRequestCount']}")
    assert p9["id"]
    assert not problems, problems


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


@pytest.mark.skip(reason="DEC-01(일정 준수율 산식) 결정 전")
def test_UC_040_S04_일정_준수_칸(target, s0):
    """목록의 일정 준수 칸 (AC-040-5)."""


@pytest.mark.skip(reason="집계 서버 오류 주입과 화면 표시는 브라우저 시나리오. 5174 에서 본다")
def test_UC_040_S05_조회_실패_구분(target, s0):
    """목록은 뜨고 지표 칸 오류 표시 (E2)."""


# ------------------------------------------------------------------ UC-041


def test_UC_041_S01_다섯_축_한_화면(target, s0):
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
        if round(_total(rate) or 0, 4) != 0.5:
            problems.append(f"위험 처리율 {_total(rate)}")
    except AssertionError as exc:
        problems.append(f"위험 처리율 지표 없음: {str(exc)[:120]}")
    assert not problems, problems


def test_UC_041_S02_진척률에서_작업까지(target, s0):
    """3.2 지연·격차 경고(40%, 미제출), 계획선 100%, 연결 이슈 #204 진행중, 완료 확인 없음. 3.1 확인됨. 3.3 격차 경고 (AC-041-4)."""
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
    gap_text = " ".join(prog["warnings"] + wbs["warnings"])
    if "3.2" not in gap_text or "3.3" not in gap_text:
        problems.append(f"격차 경고에 3.2·3.3 이 없다: {prog['warnings']}")
    if not any(str(x).startswith("3.2") for x in prog["behind"]):
        problems.append(f"계획 뒤짐에 3.2 가 없다: {prog['behind']}")
    if citems["3.1"]["completionStatus"] != "CONFIRMED" or citems["3.2"]["completionStatus"] != "NONE":
        problems.append(f"완료 확인 3.1 {citems['3.1']['completionStatus']} / 3.2 {citems['3.2']['completionStatus']}")
    if not any("204" in str(v) for v in by["3.2"].values()):
        problems.append("3.2 줄에 연결 이슈 #204(진행중)가 없다")
    assert not problems, problems


def test_UC_041_S03_L3_추정(target, s0):
    """TD-PRJ-2: 일정 줄 = 날짜 있는 이슈 6건(N6 제외), 진척도 100·100·50·30·0·100. 대표 진척률 추정 표시 (AC-041-5, 값은 DEC-17)."""
    pid = s0.ids["TD-PRJ-2"]
    wbs = _get(target, s0, f"/api/projects/{pid}/wbs?at={T0}", acc="TD-ACC-C2")
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}", acc="TD-ACC-C2")
    assert wbs["source"] == "REDMINE"
    rows = [i for i in wbs["items"] if i["startDate"]]
    assert len(rows) == 6, [i["name"] for i in wbs["items"]]
    assert sorted(i["progress"] for i in rows) == [0, 30, 50, 100, 100, 100]
    assert prog["level"] == "L3" and prog["representative"] is not None, prog
    assert "추정" in str(prog) or "L1" in str(prog["warnings"]), "추정 표시·L1 아님 경고가 없다"


def test_UC_041_S04_재료_없음(target, s0):
    """TD-PRJ-3: 진척 산출 안 함, 카드 데이터 없음, 스냅샷 산정 불가 (AC-041-5·6). API 부분."""
    pid = s0.ids["TD-PRJ-3"]
    prog = _get(target, s0, f"/api/projects/{pid}/progress?at={T0}")
    assert prog["representative"] is None, f"재료 없는 사업의 진척이 {prog['representative']} 로 산출됐다(DEF-V003)"
    assert prog["wbs"]["value"] is None and prog["issue"]["value"] is None


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
    """TD-PRJ-9: L2 11.7% 추정 / MISS 3.4 해당 없음·30.0% / SUM 경고·27.3% (AC-041-3·5, AC-030-3)."""
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
    if prog["representative"] is None or round(prog["representative"], 4) != 0.1173 or "추정" not in str(prog):
        problems.append(f"L2: {prog['representative']} level={prog['level']}")
    assert not problems, problems


@pytest.mark.skip(reason="DEC-01(일정 준수율) 결정 전")
def test_UC_041_S07_일정_준수율(target, s0):
    """일정 준수율 카드 (AC-041-9)."""


@pytest.mark.skip(reason="DEC-02(결함 기준) 결정 전")
def test_UC_041_S08_결함_처리율(target, s0):
    """결함 처리율 카드 (AC-041-10)."""


@pytest.mark.skip(reason="집계 오류 주입과 카드 표시는 브라우저 시나리오")
def test_UC_041_S10_조회_실패(target, s0):
    """그 카드만 오류·재시도 (AC-041-11)."""


@pytest.mark.skip(reason="실모델이 필요하다. 온프레미스 모델 선정 뒤 5174 에서 본다")
def test_UC_041_S11_AI_와_일치(target, s0):
    """카드 값 vs AI 집계 답 (AC-041-2)."""


# ------------------------------------------------------------------ UC-042


FIVE_AXES = [
    ("STAT_CARD", "progress_representative_pct", []),
    ("STAT_CARD", "schedule_variance_pct", []),
    ("STAT_CARD", "issue_resolution_rate", []),
    ("BAR_CHART", "open_risk_count", ["risk_severity"]),
    ("STAT_CARD", "work_product_approval_rate", []),
]


def test_UC_042_S01_추천_구성(target, s0):
    """다섯 축 카드가 서버에 저장되고 값이 집계와 같으며 다른 세션에서도 같다 (AC-042-1·4)."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    boards = _get(target, s0, f"/api/dashboards?projectId={pid}")
    board = next(b for b in boards if b["isDefault"])
    made = []
    for template, measure, dims in FIVE_AXES:
        res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec(measure, dims, [pid], template, f"TST {measure}")}, headers=c1)
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
    other = s0.login(d.ACCOUNTS["TD-ACC-C1"].username, __import__("tests.fixtures.im009.seed", fromlist=["PASSWORD"]).PASSWORD)
    detail = target.get(f"/api/dashboards/{board['id']}", headers={"Authorization": f"Bearer {other}"}).json()
    assert {w["id"] for w in detail["widgets"]} >= {w["id"] for w in made}
    assert [g["i"] for g in detail["layout"]["lg"]] and len(detail["layout"]["lg"]) >= len(made)


def test_UC_042_S02_없는_짝(target, s0):
    """지표 「없는키」 저장 → 거절 (AC-042-2)."""
    pid = s0.ids["TD-PRJ-1"]
    boards = _get(target, s0, f"/api/dashboards?projectId={pid}")
    board = next(b for b in boards if b["isDefault"])
    res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec("없는키", [], [pid])}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 400, res.text
    res = target.post(f"/api/dashboards/{board['id']}/widgets", json={"spec": _spec("open_risk_count", ["없는차원"], [pid])}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 400, res.text


@pytest.mark.skip(reason="가짜 모델은 자연어를 명세로 바꾸지 못한다(NOT_EXPRESSIBLE). 실모델로 5174 에서 본다")
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


def test_UC_043_S01_목록_원천(target, s0):
    """일반 이슈 9, 열림 3, 해결 6(66.7%). 각 행 원천(도구·연결·번호)·링크 (AC-043-1·4)."""
    pid = s0.ids["TD-PRJ-1"]
    summary = _get(target, s0, f"/api/projects/{pid}/issues/summary")
    rows = _get(target, s0, f"/api/projects/{pid}/issues?size=100")["content"]
    problems: list[str] = []
    if summary["total"] != 9 or summary["open"] != 3 or summary["closed"] != 6:
        problems.append(f"요약 전체 {summary['total']}·열림 {summary['open']}·해결 {summary['closed']} (기대 9·3·6, 결함 2건 분리는 DEC-02)")
    if len(rows) != summary["total"]:
        problems.append(f"목록 {len(rows)} ≠ 요약 {summary['total']}")
    for r in rows:
        src = r["source"]
        if not (src.get("tool") and src.get("connectionName") and (src.get("number") or src.get("externalId")) and src.get("externalUrl")):
            problems.append(f"원천 표기 부족: {r['key']} {src}")
            break
    assert not problems, problems


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


@pytest.mark.skip(reason="DEC-02(결함 기준) 결정 전. 리스크 목록 API 는 별도 확인")
def test_UC_043_S05_리스크_결함(target, s0):
    """리스크 2(열림 1 높음), 위험 처리율 50.0% (AC-043-6)."""


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
    """S1: 09-25 행 30.0/72.9 → 09-26 행 39.0/73.4. 전일 대비 +9.0%p·+0.5%p (AC-041-8, IM-009 7.1)."""
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
