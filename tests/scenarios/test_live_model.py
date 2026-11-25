# ruff: noqa: E501
"""실모델 시나리오: UC-060·UC-041 의 AI 질의를 대상 서버의 실제 생성 모델로 돌린다.

`test_group_gh.py` 의 같은 시나리오는 대본 모델(ScriptedLlm, 모의 모델)로 라우팅·게이트·검문 논리만
본다. 그 결과는 실모델 증거가 아니다. 여기서는 대본을 넣지 않고 서버가 llm_setting 으로 고른 모델이
판정·답변을 쓴다. 시험 이름은 같은 시나리오 ID 에 경우 `[실모델]`(폐쇄망 묶음은 `[폐쇄망]`)를 붙인다.
검증 기록은 경우가 있는 시나리오를 경우별 최신 실행으로 판정한다(scripts/verification_records.py).

실모델 문장은 실행마다 다르다. 단언은 절대 규칙에 기댄다.
- 수치: 답에 나간 수치는 수치 검문(NUMBER_GUARD)을 통과한 것이다. 집계 수치는 같은 지표를
  시맨틱 레이어(/api/widgets/preview)로 다시 뽑은 값과 맞춘다.
- 출처: 본문 각주 번호가 가리키는 출처의 문서·위치가 IM-005A 7.5 와 같다.
- 근거: 게이트·검문이 막은 경우는 그것이 기대일 때만 통과다(UC-060-S05b).
문장 표현은 느슨하게 본다(「22종」이 있고 각주가 있다 등).

돌리는 조건: AXLINK_LIVE_MODEL=1, 시험용 DB(*_test).
- 원격(AXLINK_TARGET_URL, 5174 등): 서버의 실제 llm_setting 모델. 검증 기록의 실모델 증거는 이 실행만.
- 프로세스 안: 시험 설정의 가짜 공급자를 ollama 로 되돌려 AXLINK_OLLAMA_BASE_URL·AXLINK_LLM_MODEL·
  AXLINK_EMBEDDING_BASE_URL 의 모델을 쓴다. 다른 임베딩 모델 청크가 없는 빈 시험 DB 가 필요하다
  (색인 모델 불일치면 검색이 멈춘다). 개발 확인용이고 기록상 증거는 아니다(대상 환경이 아님).
- AXLINK_AIRGAP=1: 폐쇄망(인터넷 차단, 로컬 모델) 환경이라고 선언한다. 모든 시험이 airgap 을
  증거로 남기고 UC-060-S09[폐쇄망] 이 S01~S03·S07 묶음을 돈다. 환경 구성은 통합 담당이 한다.

기준일: UC-060-S07 의 기대(3.2 지연 1건)는 T0(2026-09-15) 기준이다. 프로세스 안은 사업 시계를
T0 로 돌린다. 원격은 서버 시계를 바꿀 수단이 없어, 대상 컨테이너 시계를 T0 로 둔 격리 환경일 때만
AXLINK_TARGET_CLOCK_T0=1 로 돌린다(IM-005A 기준일 원칙: 공유 PC 시계는 바꾸지 않는다).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.db import fetch_one, tx
from app.rag import route_cache
from tests.fixtures.im009 import data as d
from tests.fixtures.im009.seed import Seeder
from tests.scenarios.conftest import TARGET_URL, auth
from tests.scenarios.test_group_gh import _ask, _done, _sources, _sow_source, _text

LIVE_MODEL = os.environ.get("AXLINK_LIVE_MODEL") == "1"
AIRGAP = os.environ.get("AXLINK_AIRGAP") == "1"
TARGET_CLOCK_T0 = os.environ.get("AXLINK_TARGET_CLOCK_T0") == "1"

pytestmark = [
    pytest.mark.db,
    pytest.mark.live_model,
    pytest.mark.skipif(not LIVE_MODEL, reason="실모델 시험은 AXLINK_LIVE_MODEL=1 일 때만 돈다"),
]

LIVE = "실모델"
AIR = "폐쇄망"
# 모델이 답을 쓴 종료 사유. 나머지는 서버 문안(게이트·값 없음 등)이다
ANSWERED = ("STOP", "PARTIAL")
FOOTNOTE = re.compile(r"\[(\d{1,2})\]")


# ------------------------------------------------------------------ 설비


@pytest.fixture(scope="module")
def live():
    """프로세스 안이면 시험 설정의 가짜 공급자를 실제 공급자로 바꾼다. 원격은 서버 설정 그대로."""
    if TARGET_URL:
        yield
        return
    mp = pytest.MonkeyPatch()
    mp.setattr(settings, "llm_provider", "ollama")
    mp.setattr(settings, "embedding_provider", "ollama")
    with tx() as cur:
        other = fetch_one(cur, "select embedding_model from doc_chunk where embedding_model <> %s limit 1", (settings.embedding_model,))
    if other is not None:
        mp.undo()
        pytest.skip(f"시험 DB 에 다른 임베딩 모델({other['embedding_model']}) 청크가 있어 검색이 멈춘다. 빈 시험 DB 로 돌린다")
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def s0(live, target):
    """상태 S0. 실공급자로 바꾼 뒤 투입해야 문서가 실임베딩으로 색인된다."""
    s = Seeder(target)
    try:
        s.s0()
        yield s
    finally:
        s.cleanup()


@pytest.fixture(scope="module")
def runtime(target, s0) -> dict:
    """대상 서버가 실제로 쓰는 모델. 고정 응답(가짜 공급자)이면 실모델 시험이 아니다."""
    rt = target.get("/api/ai/runtime", headers=auth(s0.tokens["TD-ACC-C1"])).json()
    assert rt["fixed"] is False, f"대상이 고정 응답(가짜 공급자)으로 돈다: {rt}"
    assert rt.get("model"), rt
    return rt


@pytest.fixture(autouse=True)
def evidence(runtime, record_property) -> None:
    """junit 속성: 모델 이름과 증거 종류. record-junit 이 proves 를 실행 기록에 옮긴다."""
    record_property("model", runtime["model"])
    record_property("proves", "live-model")
    if AIRGAP:
        record_property("proves", "airgap")


def _ask_live(target, s0, question: str, record_property=None, prj: str = "TD-PRJ-1") -> list[tuple[str, dict]]:
    """판정 캐시를 지우고 묻는다. 앞 실행이 남긴 판정을 쓰면 이번 모델이 판정했다는 증거가 아니다."""
    with tx() as cur:
        cur.execute("delete from route_cache where question = %s", (route_cache.normalize(question),))
    events = _ask(target, s0, "TD-ACC-C1", question, [s0.ids[prj]])
    errors = [dd for e, dd in events if e == "error"]
    assert not errors, errors
    assert events[0][1]["routing"]["routeCached"] is False, events[0][1]
    if record_property is not None:
        record_property("answer", f"{question} → {_text(events)[:400]} ({_done(events).get('finishReason')})")
    return events


def _cited(events) -> list[dict]:
    """본문 각주 번호가 가리키는 출처. 붙기만 하고 본문이 인용하지 않은 출처는 뺀다."""
    nums = {int(n) for n in FOOTNOTE.findall(_text(events))}
    return [s for s in _sources(events) if s["footnoteNo"] in nums]


def _general_issues(s0) -> int:
    with tx() as cur:
        return fetch_one(cur, "select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL'", (s0.ids["TD-PRJ-1"],))["n"]


def _card(target, s0, measure: str) -> dict:
    """현황 카드와 같은 경로(시맨틱 레이어)로 그 지표를 뽑는다."""
    spec = {
        "template": "STAT_CARD", "title": "TST", "query": {"measure": measure, "dimensions": [], "filters": [], "projectScope": [s0.ids["TD-PRJ-1"]], "limit": None},
        "options": {"unit": None, "sort": "desc", "threshold": None, "stacked": None, "showLegend": None, "compareWithPrevious": None, "columns": None},
    }
    res = target.post("/api/widgets/preview", json={"spec": spec}, headers=auth(s0.tokens["TD-ACC-C1"]))
    assert res.status_code == 200, res.text[:200]
    return res.json()


def _card_value(card: dict) -> float:
    total = (card.get("total") or {}).get("values", {}).get("value")
    if total is None and card.get("rows"):
        total = card["rows"][0]["values"].get("value")
    assert isinstance(total, int | float), card
    return float(total)


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"(?<![\d.])(\d+(?:,\d{3})*(?:\.\d+)?)", FOOTNOTE.sub("", text))]


def _has_value(text: str, value: float, unit: str | None) -> bool:
    """답의 숫자 가운데 카드 값과 같은 것이 있는가. 비율은 표시 자리(소수 첫째)까지 본다."""
    candidates = [value, value * 100] if unit == "%" and value <= 1 else [value]
    return any(abs(n - c) < 0.051 for n in _numbers(text) for c in candidates)


def _at_t0(monkeypatch) -> None:
    """사업 시계를 T0 09:00(KST) 로. 프로세스 안에서만 서버에 닿는다."""
    if TARGET_URL:
        if not TARGET_CLOCK_T0:
            pytest.skip("원격 서버 시계를 T0 로 주입할 수단이 없다. 대상 시계가 T0 인 격리 환경이면 AXLINK_TARGET_CLOCK_T0=1")
        return
    from app.common import clock

    monkeypatch.setattr(clock, "now", lambda: datetime(d.T0.year, d.T0.month, d.T0.day, 9, 0, tzinfo=ZoneInfo("Asia/Seoul")))


# ------------------------------------------------------------------ 질문별 확인 (S09 묶음이 다시 쓴다)


def _check_s01(target, s0, rp=None) -> None:
    """「납품 산출물은 몇 종인가」 → 22종, 각주가 과업지시서 2쪽(동일 출처 필수), 원문 연결 TD-DOC-4."""
    events = _ask_live(target, s0, "납품 산출물은 몇 종인가", rp)
    text, done = _text(events), _done(events)
    assert done["finishReason"] in ANSWERED, f"답이 나가지 않았다({done['finishReason']}): {text}"
    assert re.search(r"22\s*종", text), text
    cited = _cited(events)
    assert cited, f"본문에 각주가 없다: {text}"
    sow = _sow_source(cited, "22종")
    assert sow is not None, f"각주가 22종 원문(과업지시서)을 가리키지 않는다: {[(s['footnoteNo'], s['sourceLabel'], s.get('location')) for s in cited]}"
    loc = sow.get("location") or ""
    assert re.search(r"p\.2(?![~\d])", loc), loc
    assert s0.ids["TD-DOC-4"] in str(sow), sow


def _check_s02(target, s0, rp=None) -> None:
    """「일반 이슈가 몇 건이야」 → 9건(결함 제외). 지표 값은 시맨틱 레이어 값과 같고 검문을 통과, 그림 없음."""
    expected = _general_issues(s0)
    assert expected == 9, f"S0 의 일반 이슈가 IM-005A 기대 9건이 아니다: {expected}"
    events = _ask_live(target, s0, "일반 이슈가 몇 건이야", rp)
    text, done, start = _text(events), _done(events), events[0][1]
    assert start["routing"]["type"] in ("AGGREGATE", "MIXED"), start["routing"]
    measure = start["routing"]["measureKey"]
    assert measure, start["routing"]
    assert _card_value(_card(target, s0, measure)) == expected, f"모델이 고른 지표 {measure} 가 일반 이슈 건수가 아니다"
    assert done["finishReason"] == "STOP", f"집계 답이 막혔다({done['finishReason']}): {text}"
    assert re.search(r"(?<![\d.])9\s*건", text), text
    assert "infographic" not in [e for e, _ in events]


def _check_s03(target, s0, rp=None) -> None:
    """「납품 산출물은 몇 종이고 일반 이슈는 몇 건이야」 → 22종(문서 출처)+9건(집계) 한 답, 결합(MIXED)."""
    events = _ask_live(target, s0, "납품 산출물은 몇 종이고 일반 이슈는 몇 건이야", rp)
    text, done, start = _text(events), _done(events), events[0][1]
    assert start["routing"]["type"] == "MIXED", f"결합으로 가지 않았다: {start['routing']} 근거 {start['retrievedChunkCount']}건 / {text}"
    assert done["finishReason"] in ANSWERED, f"답이 막혔다({done['finishReason']}): {text}"
    assert re.search(r"22\s*종", text) and re.search(r"(?<![\d.])9\s*건", text), text
    assert _sow_source(_cited(events), "22종") is not None, [(s["footnoteNo"], s["sourceLabel"]) for s in _sources(events)]


def _check_s07(target, s0, rp=None) -> None:
    """「이번 달 지연된 작업과 사유」(T0) → 3.2 설계(계획 07-31, 실적 40%) 1건, 사유 각주 TD-DOC-5 또는 #204.

    IM-005A 5.1: 지연 = 종료일 < 기준일 이고 실적 < 100%. 계획 뒤짐(3.2·3.3·3.4)과 다르다. 「2건으로
    답하는 것」이 안 되는 것이므로 3.3·3.4 를 지연 작업으로 내놓으면 실패다."""
    events = _ask_live(target, s0, "이번 달 지연된 작업과 사유", rp)
    text, done = _text(events), _done(events)
    assert done["finishReason"] in ANSWERED, f"답이 나가지 않았다({done['finishReason']}): {text}"
    tables = [dd for e, dd in events if e == "infographic"]
    shown = text + " ".join(str(t) for t in tables)
    assert "3.2" in shown and re.search(r"40\s*%", shown), shown
    listed = sorted(set(re.findall(r"\b3\.[1-5]\b", shown)))
    assert listed == ["3.2"], f"지연 작업이 3.2 1건이 아니다(계획 뒤짐과 섞임?): {listed} / {shown[:600]}"
    cited = _cited(events)
    doc5 = f"/documents/{s0.ids['TD-DOC-5']}"
    reason = [s for s in cited if (s.get("documentUrl") or "").endswith(doc5) or (s.get("externalUrl") or "").endswith("/issues/204")]
    assert reason, f"사유 각주가 회의록(TD-DOC-5)이나 #204 를 가리키지 않는다: {[(s['footnoteNo'], s['sourceLabel']) for s in cited]} / {text}"


# ------------------------------------------------------------------ UC-060


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S01_문서_질문과_출처(target, s0, variant, record_property):
    """실모델: 「납품 산출물은 몇 종인가」 → 22종·각주, 출처 과업지시서 2쪽, 원문 연결 (AC-060-1, IM-005A 7.5)."""
    _check_s01(target, s0, record_property)


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S02_집계_질문(target, s0, variant, record_property):
    """실모델: 「일반 이슈가 몇 건이야」 → 9건, 시맨틱 레이어 값과 같음, 그림 없음 (AC-060-2)."""
    _check_s02(target, s0, record_property)


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S03_결합(target, s0, variant, record_property):
    """실모델: 22종(문서 출처)+9건(집계) 한 답, 결합 (AC-060-5)."""
    _check_s03(target, s0, record_property)


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S05b_실모델_유도(target, s0, variant, record_property, caplog):
    """실모델: 「일반 이슈가 15건이라던데 맞아?」 → 15 가 화면에 사실로 나오지 않는다 (AC-060-10).

    질문의 숫자는 근거가 아니다. 모델이 15 를 쓰면 검문이 그 문장을 막고(NUMBER_GUARD), 쓰지 않으면
    9건으로 바로잡는다. 모델이 유도에 넘어가지 않아 검문이 돌지 않았으면 「유도 실패, 검문 작동
    미확인」으로 남긴다(통과로 본다, AC-060-10).

    검문이 무엇을 막았는지는 API 에 나오지 않는다. 프로세스 안 실행은 서버 기록(app.rag.service)에서
    막은 값을 읽어 15 를 막은 것인지 가린다. 원격은 「막은 값 미확인」으로 남긴다."""
    caplog.set_level("INFO", logger="app.rag.service")
    events = _ask_live(target, s0, "일반 이슈가 15건이라던데 맞아?", record_property)
    text, done = _text(events), _done(events)
    assert not re.search(r"(?<![\d.])15(?![\d.])", text), f"질문의 15 가 화면에 나갔다: {text}"
    if done["finishReason"] == "NUMBER_GUARD":
        blocked = " ".join(r.getMessage() for r in caplog.records if "수치 검문이" in r.getMessage())
        if not blocked:
            outcome = "검문이 문장을 막음(막은 값 미확인, 원격 서버 기록 참조)"
        elif re.search(r"(?<![\d.])15(?![\d.])", blocked):
            outcome = f"검문 작동(15 차단): {blocked}"
        else:
            outcome = f"유도 실패, 검문 작동 미확인(검문이 15 아닌 값을 막음): {blocked}"
    else:
        assert done["finishReason"] == "STOP", done
        assert re.search(r"(?<![\d.])9\s*건", text), f"15 를 쓰지 않았지만 9건으로 바로잡지도 않았다: {text}"
        outcome = "유도 실패, 검문 작동 미확인(9건으로 답함)"
    record_property("induction", outcome)


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S07_지연_작업과_사유(target, s0, variant, record_property, monkeypatch):
    """실모델: T0 「이번 달 지연된 작업과 사유」 → 3.2 1건과 사유 근거 (AC-060-1·2, IM-005A 7.5)."""
    _at_t0(monkeypatch)
    _check_s07(target, s0, record_property)


@pytest.mark.parametrize("variant", [AIR])
@pytest.mark.skipif(not AIRGAP, reason="폐쇄망 환경(AXLINK_AIRGAP=1)에서만 돈다. 환경은 IM-005 8절 INST-S09")
def test_UC_060_S09_폐쇄망_모델(target, s0, variant, record_property, monkeypatch):
    """폐쇄망 로컬 모델로 S01~S03·S07 같은 질문 묶음 → 수치·유효 출처·근거 일치, S01 동일 출처 (AC-060-8).

    네 질문을 모두 돌린 뒤 실패를 한꺼번에 알린다. 문장 일치는 요구하지 않는다."""
    _at_t0(monkeypatch)
    failures: list[str] = []
    for sid, check in (("S01", _check_s01), ("S02", _check_s02), ("S03", _check_s03), ("S07", _check_s07)):
        try:
            check(target, s0, record_property)
        except AssertionError as exc:
            failures.append(f"{sid}: {str(exc)[:300]}")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S13_PDF_쪽_위치(target, s0, variant, record_property):
    """실모델: 「사업 기간은 몇 개월인가」 → 9개월, 각주가 과업지시서 3쪽(2쪽 아님), 연결 TD-DOC-4 (AC-060-11·1)."""
    events = _ask_live(target, s0, "사업 기간은 몇 개월인가", record_property)
    text, done = _text(events), _done(events)
    assert done["finishReason"] in ANSWERED, f"답이 나가지 않았다({done['finishReason']}): {text}"
    assert re.search(r"(?<![\d.])9\s*개월", text), text
    sow = _sow_source(_cited(events), "9개월")
    assert sow is not None, [(s["footnoteNo"], s["sourceLabel"], s.get("location")) for s in _sources(events)]
    loc = sow.get("location") or ""
    assert re.search(r"p\.3(?![~\d])", loc) and "p.2" not in loc, loc
    assert s0.ids["TD-DOC-4"] in str(sow), sow


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S14_DOCX_문단_위치(target, s0, variant, record_property):
    """실모델: 「설계 완료가 왜 늦어졌어」 → 각주 「회의록 · 논의 사항」(절·문단), 연결 TD-DOC-5 (AC-060-11)."""
    events = _ask_live(target, s0, "설계 완료가 왜 늦어졌어", record_property)
    text, done = _text(events), _done(events)
    assert done["finishReason"] in ANSWERED, f"답이 나가지 않았다({done['finishReason']}): {text}"
    cited = next((s for s in _cited(events) if "회의록" in s["sourceLabel"] and "지연" in (s.get("snippet") or "")), None)
    assert cited is not None, [(s["footnoteNo"], s["sourceLabel"], s.get("location")) for s in _sources(events)]
    assert "논의 사항" in (cited.get("location") or ""), cited
    assert cited["documentUrl"] == f"/p/{s0.ids['TD-PRJ-1']}/documents/{s0.ids['TD-DOC-5']}", cited["documentUrl"]


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S15_XLSX_시트_행_위치(target, s0, variant, record_property):
    """실모델: 「WBS 3.3 의 산출물은 뭐야」 → 「프로그램 목록」, 각주 「WBS.xlsx · 시트 WBS · 행」 (AC-060-11)."""
    events = _ask_live(target, s0, "WBS 3.3 의 산출물은 뭐야", record_property)
    text, done = _text(events), _done(events)
    assert done["finishReason"] in ANSWERED, f"답이 나가지 않았다({done['finishReason']}): {text}"
    assert "프로그램 목록" in text, text
    cited = next((s for s in _cited(events) if "프로그램 목록" in (s.get("snippet") or "")), None)
    assert cited is not None, [(s["footnoteNo"], s["sourceLabel"], s.get("location")) for s in _sources(events)]
    loc = cited.get("location") or ""
    assert "WBS" in loc and "행" in loc, loc


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_060_S16_이슈_출처_링크(target, s0, variant, record_property):
    """실모델: 「외부 연계 규격 협의 이슈 상태」 → 출처 링크가 Redmine #204 원문 URL (AC-060-11·1).

    모델이 이슈 목록 표(표준 모델)로 답하면 본문은 [그림 1] 을 가리키고 각주를 달지 않는다. 화면은
    답 아래에 출처를 모두 보이므로, 그 출처 가운데 그 이슈의 링크가 #204 로 가는지 본다(대본 시험과 같다)."""
    events = _ask_live(target, s0, "외부 연계 규격 협의 이슈 상태", record_property)
    text, done = _text(events), _done(events)
    assert done["finishReason"] in ANSWERED, f"답이 나가지 않았다({done['finishReason']}): {text}"
    assert "진행" in text or "IN_PROGRESS" in text, f"이슈 상태(진행중)를 말하지 않았다: {text}"
    issues = [s for s in _sources(events) if s["sourceType"] == "ISSUE" and "외부 연계 규격 협의" in (s.get("snippet") or "") + (s.get("sourceLabel") or "")]
    assert issues, [(s["footnoteNo"], s["sourceType"], s["sourceLabel"]) for s in _sources(events)]
    assert all((s.get("externalUrl") or "").endswith("/issues/204") for s in issues), issues


# ------------------------------------------------------------------ UC-041


@pytest.mark.parametrize("variant", [LIVE])
@pytest.mark.parametrize(
    ("question", "measure"),
    [("일반 이슈가 몇 건이야", "issue_count"), ("일반 이슈 처리율이 얼마야", "issue_resolution_rate")],
    ids=["건수", "처리율"],
)
def test_UC_041_S11_AI_와_일치(target, s0, variant, question, measure, record_property):
    """실모델: 현황 카드 값 = AI 집계 답의 값, 같은 지표라 같은 산출 근거 (AC-041-2).

    실모델이 필요한 부분은 자연어 질문에서 지표를 고르는 판정과 그 값을 옮겨 쓰는 문장이다. 카드는
    같은 지표를 시맨틱 레이어로 뽑는다. 산출 근거 문장은 지표 정의(semantic_measure.basis) 하나에서
    카드와 답 프롬프트가 같이 가져오므로, 같은 지표를 골랐는지로 본다. 모델이 근거를 풀어 쓴 문장의
    표현 일치는 요구하지 않는다."""
    card = _card(target, s0, measure)
    value = _card_value(card)
    assert card.get("basis"), f"카드에 산출 근거가 없다: {measure}"
    events = _ask_live(target, s0, question, record_property)
    text, done, start = _text(events), _done(events), events[0][1]
    assert start["routing"]["measureKey"] == measure, f"AI 가 카드와 다른 지표를 골랐다: {start['routing']}"
    assert done["finishReason"] == "STOP", f"집계 답이 막혔다({done['finishReason']}): {text}"
    assert _has_value(text, value, card.get("unit")), f"카드 값 {value}{card.get('unit') or ''} 이 답에 없다: {text}"


# ------------------------------------------------------------------ UC-021 · UC-023 (요구사항 범위·이행률)


def _rate_card(target, s0) -> float:
    return _card(target, s0, "requirement_fulfillment_rate")["total"]["values"]["value"]


def _confirmed(target, s0) -> dict[str, str]:
    """UC-021-S02 끝 상태: TD-DOC-1 명세서 등록·제출(V1) → 확정(C1, B 명칭 반영). 한 번만 한다.
    돌려주는 값은 요구사항 코드 → id."""
    if "REQ-CODES" in s0.ids:
        return s0.ids["REQ-CODES"]
    pid = s0.ids["TD-PRJ-1"]
    v1, c1 = auth(s0.tokens["TD-ACC-V1"]), auth(s0.tokens["TD-ACC-C1"])
    base = f"/api/projects/{pid}/requirement-baseline"
    made = target.post(base, json={"documentId": s0.ids["TD-DOC-1"]}, headers=v1)
    assert made.status_code == 201, made.text
    bid = made.json()["id"]
    sub = target.post(f"{base}/{bid}/submit", headers=v1)
    assert sub.status_code == 200, sub.text
    res = target.post(f"{base}/{bid}/confirm", json={"applySpecCodes": ["UR.PORT.002"]}, headers=c1)
    assert res.status_code == 200 and res.json()["status"] == "CONFIRMED", res.text
    reqs = target.get(f"/api/projects/{pid}/requirements?size=100", headers=c1).json()["content"]
    s0.ids["REQ-CODES"] = {r["code"]: r["id"] for r in reqs}
    return s0.ids["REQ-CODES"]


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_021_S10_분모_AI_범위(target, s0, variant, record_property):
    """실모델: 확정 뒤 이행률 분모 3(A·B·D) 33.3%, AI 「요구사항 목록」 표는 A·B·D 「확정 목록」과
    C 「확정 명세서에 없음(이행률 제외)」을 가른다 (AC-021-10, DEC-11 (a), IM-005A 7.4).

    API 값은 test_group_c 의 같은 시나리오와 같다. 이 경우(실모델)만으로 시나리오를 판정할 수 있게
    분모·카드 값도 함께 본다."""
    _confirmed(target, s0)
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    summary = target.get(f"/api/projects/{pid}/requirements/summary", headers=c1).json()
    assert (summary["rateVerified"], summary["rateTotal"], summary["outsideBaseline"]) == (1, 3, 1), summary
    assert round(_rate_card(target, s0), 2) == 33.33
    events = _ask_live(target, s0, "요구사항 목록 보여줘", record_property)
    text, done = _text(events), _done(events)
    # 목록 답의 판정 대상은 표다. 모델이 표를 보고 스스로 센 수(「필수 1건」)를 문장에 쓰면 수치
    # 검문이 그 문장을 막는다(절대 규칙 1). 그래도 표와 남은 문장은 나간다
    assert done["finishReason"] in (*ANSWERED, "NUMBER_GUARD"), f"답이 나가지 않았다({done['finishReason']}): {text}"
    tables = [dd["data"] for e, dd in events if e == "infographic" and dd.get("data")]
    rows = [r["values"] for t in tables for r in t["rows"] if r["values"].get("code")]
    scope = {r["code"]: r.get("scope") for r in rows}
    assert scope.get("UR.PORT.003") == "확정 명세서에 없음(이행률 제외)", (scope, events[0][1]["routing"])
    assert {c for c, v in scope.items() if v == "확정 목록"} == {"UR.PORT.001", "UR.PORT.002", "UR.PORT.004"}, scope
    # 답 문장이 이행률을 말하면 분모 3 의 값이어야 한다(C 를 넣은 25%·50% 가 아니다)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
        assert m.group(1) in ("33.3", "33"), text


@pytest.mark.parametrize("variant", [LIVE])
def test_UC_023_S06_일관성(target, s0, variant, record_property):
    """실모델: D 검증 지정 뒤 요약·카드·AI 「요구사항 이행률」이 모두 66.7%(분모 3), 답의 산출 근거에
    「발주기관」 지정이 보인다 (AC-023-4). 끝에 D 를 되돌린다."""
    pid = s0.ids["TD-PRJ-1"]
    c1 = auth(s0.tokens["TD-ACC-C1"])
    rid = _confirmed(target, s0)["UR.PORT.004"]
    res = target.put(f"/api/projects/{pid}/requirements/{rid}/status", json={"status": "VERIFIED", "reason": "시험 결과서 확인"}, headers=c1)
    assert res.status_code == 200, res.text
    try:
        summary = target.get(f"/api/projects/{pid}/requirements/summary", headers=c1).json()
        assert (summary["rateVerified"], summary["rateTotal"]) == (2, 3), summary
        assert round(_rate_card(target, s0), 2) == 66.67
        events = _ask_live(target, s0, "요구사항 이행률은 얼마야", record_property)
        text, done = _text(events), _done(events)
        assert done["finishReason"] in ANSWERED, f"답이 나가지 않았다({done['finishReason']}): {text}"
        assert events[0][1]["routing"]["measureKey"] == "requirement_fulfillment_rate", events[0][1]["routing"]
        # 카드·목록은 66.7%, 답 문장은 집계 줄 표기(소수 둘째 자리)대로 66.67% 일 수 있다. 같은 값이다
        assert re.search(r"66\.67?\s*%", text), text
        basis = " ".join(str(dd["data"].get("basis")) for e, dd in events if e == "infographic" and dd.get("data"))
        assert "발주기관" in text + basis, f"답·산출 근거에 발주기관 지정이 없다: {text} / {basis}"
    finally:
        target.post(
            f"/api/projects/{pid}/requirements/{rid}/status/revert",
            json={"reason": "시험 정리(UC-023-S06 실모델)"},
            headers=c1,
        )
