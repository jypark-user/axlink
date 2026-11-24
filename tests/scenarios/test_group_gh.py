# ruff: noqa: E501
"""G·H 그룹: AI 질의·모델 설정 (UC-060·061) 과 자료 (UC-070) 예제 시나리오.

모델은 대본대로 답하는 흉내(ScriptedLlm)다. 여기서 보는 것은 라우팅·게이트·수치 검문·출처 위치가
설계대로 움직이는지이고, 문장 품질과 실모델 일치(AC-060-8·10)는 5174 실모델에서 본다.
PDF(TD-DOC-4·7·16)·HWP·HWPX(TD-DOC-12·13·15)는 커밋해 둔 가상 시험자료다(fixtures/im009/pdf·hwp).
손상(TD-DOC-10)·대용량(TD-DOC-11) 자료는 생성기가 없어 「자료 없음」으로 보류한다(files.MISSING).
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import time
import uuid
from collections.abc import Iterator

import httpx
import pytest

from app.ai.port import LlmResult
from app.common import errors
from app.config import settings
from app.db import fetch_all, fetch_one, tx
from app.rag import answer as ask_answer
from app.rag import number_guard
from app.rag import search as ask_search
from app.rag import service as ask_service
from tests.fixtures.im009 import replay_ollama
from tests.scenarios.conftest import TARGET_URL, auth

pytestmark = pytest.mark.db

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# 실제 어댑터(app/ai/llm.py)가 연결 실패 때 내는 오류와 같은 꼴
_DOWN = errors.ApiError(503, "AI_UNAVAILABLE", "LLM 에 닿지 못했습니다: [Errno 111] Connection refused")


class ScriptedLlm:
    """라우팅 답(JSON)과 본문을 대본으로 받는다. 몇 번 불렸는지 센다."""

    def __init__(self, route: dict | None, text: str, fail: bool = False) -> None:
        self.route, self.text, self.fail = route, text, fail
        self.stream_calls = 0
        self.complete_calls = 0

    def complete(self, system: str, user: str, *, json_schema=None) -> LlmResult:
        self.complete_calls += 1
        if self.fail:
            raise _DOWN
        text = json.dumps(self.route, ensure_ascii=False) if self.route else "모르겠다"
        return LlmResult(text=text, model="scripted")

    def stream(self, system: str, user: str, *, json_schema=None) -> Iterator[str]:
        self.stream_calls += 1
        if self.fail:
            raise _DOWN
        raw = json.dumps({"answer": self.text}, ensure_ascii=False) if json_schema else self.text
        for i in range(0, len(raw), 7):
            yield raw[i : i + 7]


def _events(res) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    name, data = "message", []
    for line in [*res.iter_lines(), ""]:
        if line == "":
            if data:
                out.append((name, json.loads("\n".join(data))))
            name, data = "message", []
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
    return out


def _conversation(target, s0, acc: str, scope: list[str]):
    return target.post("/api/conversations", json={"title": "시험 대화", "projectScope": scope}, headers=auth(s0.tokens[acc]))


def _ask(target, s0, acc: str, question: str, scope: list[str]) -> list[tuple[str, dict]]:
    conv = _conversation(target, s0, acc, scope)
    assert conv.status_code == 201, conv.text
    with target.stream("POST", f"/api/conversations/{conv.json()['id']}/messages", json={"question": question, "projectScope": []}, headers={**auth(s0.tokens[acc]), "Accept": "text/event-stream"}) as res:
        assert res.status_code == 200, res.read()
        return _events(res)


def _text(events) -> str:
    return "".join(dd["text"] for e, dd in events if e == "delta")


def _sources(events) -> list[dict]:
    return next((dd["sources"] for e, dd in events if e == "sources"), [])


def _done(events) -> dict:
    return events[-1][1]


class RemoteScriptedLlm:
    """원격 대상의 대본 모델. 재생 서버(replay_ollama)에 대본을 넣고 호출 수를 거기서 읽는다."""

    def __init__(self, base: str) -> None:
        self._base = base

    def script(self, route: dict | None, text: str, fail: bool = False) -> None:
        res = httpx.put(f"{self._base}/ollama/_script", json={"route": route, "text": text, "fail": fail}, timeout=10)
        res.raise_for_status()

    def _calls(self) -> dict:
        return httpx.get(f"{self._base}/ollama/_calls", timeout=10).json()

    @property
    def stream_calls(self) -> int:
        return self._calls()["stream"]

    @property
    def complete_calls(self) -> int:
        return self._calls()["complete"]


@pytest.fixture
def llm(monkeypatch, record_property):
    """대본 모델(모의 모델: 장애·오류 처리 검증용, 실모델 검증 아님). 프로세스 안은 llm_port 를 바꾸고, 원격(remote_llm 표시)은 시험 DB 의 llm_setting 을
    재생 서버의 Ollama 흉내로 돌린 뒤 끝나면 되돌린다. 원격은 문턱·top_k 가 서버 설정이라 못 바꾼다:
    실제 문턱(rag_min_similarity)과 실임베딩으로 본다(min_sim 인자는 프로세스 안에서만 쓴다)."""
    if TARGET_URL:
        # 모의 모델 증거 표시(원격 실행의 junit 속성). 실모델 검증(live-model)이 아니다.
        # record-junit 은 아직 이 속성을 읽지 않는다. 프로세스 안(CI, junit xunit2)은 남기지 않는다
        record_property("model", "mock-replay")
        host = os.environ["AXLINK_REPLAY_URL"].rstrip("/")
        inner = (os.environ.get("AXLINK_REPLAY_TARGET_URL") or host).rstrip("/")
        with tx() as cur:
            before = fetch_one(cur, "select base_url, model, updated_by_user_id, updated_at from llm_setting where id = 1")
            cur.execute(
                "insert into llm_setting (id, base_url, model, updated_at) values (1, %s, %s, now()) "
                "on conflict (id) do update set base_url = excluded.base_url, model = excluded.model, updated_at = now()",
                (inner + "/ollama", replay_ollama.MODEL),
            )
        remote = RemoteScriptedLlm(host)

        def _install_remote(route: dict | None, text: str, fail: bool = False, min_sim: float = -1.0) -> RemoteScriptedLlm:
            remote.script(route, text, fail)
            return remote

        try:
            yield _install_remote
        finally:
            with tx() as cur:
                if before is None:
                    cur.execute("delete from llm_setting where id = 1")
                else:
                    cur.execute(
                        "update llm_setting set base_url = %s, model = %s, updated_by_user_id = %s, updated_at = %s where id = 1",
                        (before["base_url"], before["model"], before["updated_by_user_id"], before["updated_at"]),
                    )
        return

    def _install(route: dict | None, text: str, fail: bool = False, min_sim: float = -1.0) -> ScriptedLlm:
        scripted = ScriptedLlm(route, text, fail)
        monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
        monkeypatch.setattr(settings, "rag_min_similarity", min_sim)
        monkeypatch.setattr(settings, "rag_top_k", 20)
        return scripted
    yield _install


# ------------------------------------------------------------------ UC-060


def test_UC_060_S02_집계_질문(target, s0, llm):
    """「일반 이슈가 몇 건이야」 → 9건, 산출 근거(리스크·결함·출처 이슈 제외), 그림 없음 (AC-060-2)."""
    scripted = llm({"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"}, "일반 이슈는 모두 9건입니다.")
    events = _ask(target, s0, "TD-ACC-C1", "일반 이슈가 몇 건이야", [s0.ids["TD-PRJ-1"]])
    text, done = _text(events), _done(events)
    assert done["finishReason"] != "NUMBER_GUARD", f"9건이 집계(일반 이슈, 결함 제외)와 어긋나 막혔다: {text}"
    assert "9건" in text, text
    assert "infographic" not in [e for e, _ in events]
    assert scripted.stream_calls == 1


@pytest.mark.remote_llm
def test_UC_060_S04_근거_부족(target, s0, llm):
    """모의 모델: 장애·오류 처리 검증(근거 게이트). 「이번 달 지출 내역 알려줘」 → 생성 호출 0, 근거 부족 문안, 출처 0 (AC-060-3)."""
    scripted = llm({"route": "DOCUMENT", "query": "지출 내역"}, "지어낸 답", min_sim=0.99)
    events = _ask(target, s0, "TD-ACC-C1", "이번 달 지출 내역 알려줘", [s0.ids["TD-PRJ-1"]])
    assert scripted.stream_calls == 0
    assert _sources(events) == []
    text = _text(events)
    # 근거 부족 문안에 유사도와 문턱이 적힌다(AC-060-3)
    assert ("찾지 못" in text or "부족" in text) and "유사도" in text and "기준" in text, text
    assert "지어낸 답" not in text


@pytest.mark.remote_llm
def test_UC_060_S05a_주입_차단(target, s0, llm):
    """가짜 모델이 「이슈는 977건」 출력 → 그 문장 미출력·미저장, 종료 사유 수치 검문 (AC-060-4)."""
    with tx() as cur:
        n = fetch_one(cur, "select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL'", (s0.ids["TD-PRJ-1"],))["n"]
    scripted = llm({"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"}, f"현재 이슈는 모두 {n}건입니다. 그중 977건이 지연입니다. 확인해 보십시오.")
    conv = _conversation(target, s0, "TD-ACC-C1", [s0.ids["TD-PRJ-1"]]).json()
    with target.stream("POST", f"/api/conversations/{conv['id']}/messages", json={"question": "이슈 건수는?", "projectScope": []}, headers={**auth(s0.tokens["TD-ACC-C1"]), "Accept": "text/event-stream"}) as res:
        events = _events(res)
    deltas = [dd["text"] for e, dd in events if e == "delta"]
    assert all("977" not in piece for piece in deltas)
    assert number_guard.BLOCKED_NOTE in "".join(deltas)
    assert _done(events)["finishReason"] == "NUMBER_GUARD"
    saved = target.get(f"/api/conversations/{conv['id']}/messages", headers=auth(s0.tokens["TD-ACC-C1"])).json()
    assert "977" not in saved[1]["content"]
    assert scripted.stream_calls == 1


@pytest.mark.remote_llm
def test_UC_060_S17_잘못된_대상_결합(target, s0, llm):
    """가짜 모델이 「일반 이슈 처리율은 50%」(50 은 위험 처리율) → 그 문장 차단 (AC-060-12·4, DEC-13 무관)."""
    llm({"route": "AGGREGATE", "measure": "issue_resolution_rate", "template": "STAT_CARD"}, "일반 이슈 처리율은 50% 입니다. 확인해 주세요.")
    events = _ask(target, s0, "TD-ACC-C1", "일반 이슈 처리율이 얼마야", [s0.ids["TD-PRJ-1"]])
    text = _text(events)
    assert "50%" not in text, text
    assert _done(events)["finishReason"] == "NUMBER_GUARD", _done(events)


def test_UC_060_S06a_다른_사업_접근_거절(target, s0, screen):
    """C2 / V3 가 TD-PRJ-1 을 범위에 넣어 질문 → 서버 거절 (AC-060-6)."""
    for acc in ("TD-ACC-C2", "TD-ACC-V3"):
        res = _conversation(target, s0, acc, [s0.ids["TD-PRJ-1"]])
        assert res.status_code == 403, (acc, res.status_code, res.text[:120])
    _ui_UC_060_S06a(screen, s0)


@pytest.mark.remote_llm
def test_UC_060_S06b_배정된_용역사의_질의(target, s0, llm, screen):
    """V1 이 배정된 TD-PRJ-1 범위로 S02 질문 → 정상 답 9건 (AC-060-6, DEC-15 (a) 2026-11-13 사용자 결정).

    모의 모델: 권한 판정 확인용(실모델 검증 아님). 화면은 V1 에게 [새 질문]이 보이고 그 사업 질의
    화면이 열리는지 따로 본다. 배정되지 않은 사업 거절은 UC-060-S06a(V3)가 본다."""
    scripted = llm({"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"}, "일반 이슈는 모두 9건입니다.")
    events = _ask(target, s0, "TD-ACC-V1", "일반 이슈가 몇 건이야", [s0.ids["TD-PRJ-1"]])
    text, done = _text(events), _done(events)
    assert done["finishReason"] == "STOP", f"배정된 용역사의 질의가 정상 답으로 끝나지 않았다({done['finishReason']}): {text}"
    assert "9건" in text, text
    assert scripted.stream_calls == 1
    if not screen:
        return
    sc = screen("TD-ACC-V1")
    # 질의 화면 본문(질문 입력)과 사이드바의 [새 질문]. [새 질문]은 본문(main) 밖 사이드바에 있다
    sc.open(f"/p/{s0.ids['TD-PRJ-1']}/ask").see("무엇이든 물어보십시오")
    sc.see("새 질문", selector="body")
    sc.shot("용역사 질의 화면")
    sc.not_see("접근 권한이 없습니다")
    sc.done()


@pytest.mark.remote_llm
def test_UC_060_S08_값_없음_구분(target, s0, llm):
    """모의 모델: 장애·오류 처리 검증(값 없음 문안). TD-PRJ-3 「진척률이 얼마야」 → 「WBS 없음」 문안, 문서 경로로 안 감 (AC-060-7)."""
    scripted = llm({"route": "AGGREGATE", "measure": "progress_representative_pct", "template": "STAT_CARD"}, "진척률은 계산할 수 없습니다.")
    events = _ask(target, s0, "TD-ACC-C1", "진척률이 얼마야", [s0.ids["TD-PRJ-3"]])
    start = events[0][1]
    text = _text(events)
    assert start["routing"]["type"] != "DOCUMENT", start["routing"]
    assert ("WBS" in text or "없" in text or "산출" in text), text
    assert "0%" not in text and "0.0" not in text, f"재료 없는 사업에 0% 가 답으로 나갔다: {text}"
    assert scripted.stream_calls <= 1


_AGG_ROUTE = {"route": "AGGREGATE", "measure": "issue_count", "dimensions": [], "template": "STAT_CARD", "title": "이슈 건수", "query": "이슈 건수"}
_DOC_ROUTE = {"route": "DOCUMENT", "query": "사업 기간 개월"}


def _ask_raw(target, s0, question: str) -> list[tuple[str, dict]]:
    """장애 때는 200 이 아닐 수 있다. 상태와 상관없이 사건을 돌려준다."""
    conv = _conversation(target, s0, "TD-ACC-C1", [s0.ids["TD-PRJ-1"]])
    assert conv.status_code == 201
    with target.stream("POST", f"/api/conversations/{conv.json()['id']}/messages", json={"question": question, "projectScope": []}, headers={**auth(s0.tokens["TD-ACC-C1"]), "Accept": "text/event-stream"}) as res:
        assert res.status_code in (200, 502, 503), res.read()
        return _events(res) if res.status_code == 200 else []


def _shown(events) -> str:
    """화면에 나가는 글. delta 와 error 사건의 문장(화면은 error 문장을 그대로 보인다)."""
    return _text(events) + "".join(dd.get("message", "") for e, dd in events if e == "error")


@pytest.mark.remote_llm
@pytest.mark.parametrize(
    ("cached", "kind"),
    [(False, "aggregate"), (False, "document"), (True, "aggregate"), (True, "document")],
    ids=["캐시없음-집계", "캐시없음-문서", "캐시있음-집계", "캐시있음-문서"],
)
def test_UC_060_S10_모델_장애(target, s0, llm, cached, kind):
    """모의 모델: 장애·오류 처리 검증. 모델 서버 장애 때 집계 질문은 집계 값 서버 문안, 문서 질문은
    「쓸 수 없음」. 모델이 생성한 문장은 나가지 않는다 (AC-060-9).

    판정 캐시 있음/없음 × 집계/문서 네 경우(DEF-V041). 캐시가 없으면 판정 단계에서 장애를 알아
    생성 호출이 0회다. 캐시가 있으면 판정 단계를 건너뛰어 생성을 한 번 시도할 수 있다."""
    question = {"aggregate": "일반 이슈가 몇 건이야", "document": "사업 기간은 몇 개월인가"}[kind]
    route = _AGG_ROUTE if kind == "aggregate" else _DOC_ROUTE
    model_text = "모델이 지어낸 문장입니다." if kind == "aggregate" else "사업 기간은 9개월입니다[1]."
    with tx() as cur:
        cur.execute("delete from route_cache where question = %s", (question,))
        expected = cur.execute("select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL'", (s0.ids["TD-PRJ-1"],)).fetchone()["n"]
    if cached:
        # 모델이 살아 있을 때 한 번 답해 판정을 캐시에 남긴다(운영 상태)
        alive = llm(route, model_text if kind == "document" else "일반 이슈 건수를 알려 드립니다.")
        first = _ask(target, s0, "TD-ACC-C1", question, [s0.ids["TD-PRJ-1"]])
        assert _done(first)["finishReason"] == "STOP", first
        assert alive.stream_calls == 1
    down = llm(None, model_text, fail=True)
    events = _ask_raw(target, s0, question)
    shown = _shown(events)
    assert "Errno" not in shown, "연결 오류 원문이 화면에 나간다"
    assert model_text not in shown and "알려 드립니다" not in shown, shown
    if cached:
        assert events and events[0][1]["routing"]["routeCached"] is True, events[:1]
        assert down.stream_calls <= 1, "생성 시도는 한 번까지(AC-060-9)"
    else:
        assert down.stream_calls == 0, "판정 단계에서 장애를 알았는데 생성을 불렀다"
    if kind == "aggregate" and cached:
        assert "error" not in [e for e, _ in events], events
        assert _done(events)["finishReason"] == "MODEL_DOWN", _done(events)
        assert "쓸 수 없" in shown and str(expected) in shown, shown
    elif kind == "aggregate":
        assert ("건" in shown) or ("쓸 수 없" in shown), shown
    else:
        assert "쓸 수 없" in shown, shown
        assert _sources(events) == [], _sources(events)


def test_UC_060_S12_되묻기(target, s0, llm):
    """「비율이 얼마야」 → 선택지 되묻기, 생성 호출 0 (A4)."""
    scripted = llm({"route": "CLARIFY", "options": ["measure:issue_resolution_rate", "measure:work_product_approval_rate"]}, "")
    events = _ask(target, s0, "TD-ACC-C1", "비율이 얼마야", [s0.ids["TD-PRJ-1"]])
    assert _done(events)["finishReason"] == "CLARIFY", _done(events)
    assert scripted.stream_calls == 0
    text = _text(events)
    assert "처리율" in text or "승인률" in text or "어느" in text, text


def test_UC_060_S14_DOCX_문단_위치(target, s0, llm):
    """「설계 완료가 왜 늦어졌어」 → 출처 「회의록 · 논의 사항 · 1쪽」(절·문단), 연결 TD-DOC-5 (AC-060-11)."""
    if settings.embedding_provider == "fake":
        # 가짜 임베딩은 해시 벡터라 검색 순위가 의미 없다. 「논의 사항」 조각이 출처에 오르는지는
        # 실임베딩(bge-m3)으로 본다. 절 경로가 위치로 남는지는 tests/test_extractor_office.py 가 본다
        pytest.skip("실임베딩 필요: 가짜 임베딩에서는 검색 순위가 무작위다")
    scripted = llm({"route": "DOCUMENT", "query": "설계 완료 지연 사유"}, "외부 연계 규격 협의가 지연돼 설계 완료가 늦어졌다[1].")
    events = _ask(target, s0, "TD-ACC-C1", "설계 완료가 왜 늦어졌어", [s0.ids["TD-PRJ-1"]])
    sources = _sources(events)
    assert sources, _text(events)
    cited = next((s for s in sources if "지연" in (s.get("snippet") or "")), None)
    assert cited is not None, [s["snippet"][:40] for s in sources]
    assert "회의록" in cited["sourceLabel"] and "논의 사항" in (cited.get("location") or ""), cited
    assert cited["documentUrl"] == f"/p/{s0.ids['TD-PRJ-1']}/documents/{s0.ids['TD-DOC-5']}", cited["documentUrl"]
    assert scripted.stream_calls == 1


def test_UC_060_S15_XLSX_시트_행_위치(target, s0, llm):
    """「WBS 3.3 의 산출물은 뭐야」 → 「프로그램 목록」, 출처 「WBS.xlsx · 시트 WBS · 5행」 (AC-060-11)."""
    llm({"route": "DOCUMENT", "query": "WBS 3.3 산출물"}, "3.3 구현 작업의 산출물은 프로그램 목록이다[1].")
    events = _ask(target, s0, "TD-ACC-C1", "WBS 3.3 의 산출물은 뭐야", [s0.ids["TD-PRJ-1"]])
    sources = _sources(events)
    cited = next((s for s in sources if "프로그램 목록" in (s.get("snippet") or "")), None)
    assert cited is not None, f"저장소에서 수집한 WBS.xlsx 가 색인·검색되지 않았다: {[s.get('sourceLabel') for s in sources]}"
    loc = cited.get("location") or ""
    assert "WBS" in loc and ("5행" in loc or "행" in loc), loc


def test_UC_060_S16_이슈_출처_링크(target, s0, llm):
    """「외부 연계 규격 협의 이슈 상태」 → 출처 링크가 Redmine #204 원문 URL (AC-060-11·1)."""
    llm({"route": "DOCUMENT", "query": "외부 연계 규격 협의"}, "외부 연계 규격 협의 이슈는 진행중이다[1].")
    events = _ask(target, s0, "TD-ACC-C1", "외부 연계 규격 협의 이슈 상태", [s0.ids["TD-PRJ-1"]])
    sources = _sources(events)
    cited = next((s for s in sources if "외부 연계 규격 협의" in (s.get("snippet") or "") or "외부 연계 규격 협의" in (s.get("sourceLabel") or "")), None)
    assert cited is not None, [s.get("sourceLabel") for s in sources]
    assert cited["sourceType"] == "ISSUE" and (cited.get("externalUrl") or "").endswith("/issues/204"), cited


def _sow_source(sources: list[dict], phrase: str) -> dict | None:
    return next(
        (s for s in sources if "과업지시서" in (s.get("sourceLabel") or "") and phrase in (s.get("snippet") or "")),
        None,
    )


def _all_evidence(monkeypatch) -> None:
    """프로세스 안 실행은 가짜 임베딩(글자 해시)이라 근거 순서가 내용과 무관하게 정해진다. 조각
    본문이 조금만 바뀌어도 답이 든 조각이 상위 20개 밖으로 밀린다. 출처 위치를 보는 시나리오는
    사업 조각을 모두 근거로 넣어 순위 운에서 떼어 낸다. 원격 실행(실임베딩)에는 닿지 않는다."""
    monkeypatch.setattr(settings, "rag_top_k", 100)


def test_UC_060_S01_문서_질문과_출처(target, s0, llm, monkeypatch):
    """「납품 산출물은 몇 종인가」 → 22종·각주, 출처 과업지시서 2쪽, 원문 연결 (AC-060-1, IM-009 7.5)."""
    llm({"route": "DOCUMENT", "query": "납품 산출물 종"}, "납품 산출물은 22종입니다[1].")
    _all_evidence(monkeypatch)
    events = _ask(target, s0, "TD-ACC-C1", "납품 산출물은 몇 종인가", [s0.ids["TD-PRJ-1"]])
    text, sources = _text(events), _sources(events)
    assert "22종" in text and "[1]" in text, text
    cited = _sow_source(sources, "22종")
    assert cited is not None, [(s.get("sourceLabel"), s.get("location")) for s in sources]
    loc = cited.get("location") or ""
    # 「22종」은 2쪽에만 있다. 2~3쪽처럼 걸친 위치는 원문 위치가 아니다
    assert re.search(r"p\.2(?![~\d])", loc), loc
    assert s0.ids["TD-DOC-4"] in str(cited), cited


def test_UC_060_S03_결합(target, s0, llm):
    """「납품 산출물은 몇 종이고 일반 이슈는 몇 건이야」 → 22종(문서 출처)+9건(집계) 한 답, 결합 (AC-060-5)."""
    llm({"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD", "query": "납품 산출물 종"},
        "납품 산출물은 22종이고[1] 일반 이슈는 9건입니다.")
    events = _ask(target, s0, "TD-ACC-C1", "납품 산출물은 몇 종이고 일반 이슈는 몇 건이야", [s0.ids["TD-PRJ-1"]])
    text, done, start = _text(events), _done(events), events[0][1]
    assert start["routing"]["type"] == "MIXED", start["routing"]
    assert _sow_source(_sources(events), "22종") is not None
    assert done["finishReason"] != "NUMBER_GUARD", f"9건이 집계(일반 이슈, 결함 제외)와 어긋나 막혔다: {text}"
    assert "22종" in text and "9건" in text, text


def test_UC_060_S13_PDF_쪽_위치(target, s0, llm, monkeypatch):
    """「사업 기간은 몇 개월인가」 → 9개월, 출처 3쪽(2쪽 아님), 연결이 TD-DOC-4 (AC-060-11·1)."""
    llm({"route": "DOCUMENT", "query": "사업 기간 개월"}, "사업 기간은 9개월입니다[1].")
    _all_evidence(monkeypatch)
    events = _ask(target, s0, "TD-ACC-C1", "사업 기간은 몇 개월인가", [s0.ids["TD-PRJ-1"]])
    text, sources = _text(events), _sources(events)
    assert "9개월" in text, text
    cited = _sow_source(sources, "9개월")
    assert cited is not None, [(s.get("sourceLabel"), s.get("location")) for s in sources]
    loc = cited.get("location") or ""
    assert re.search(r"p\.3(?![~\d])", loc) and "p.2" not in loc, loc
    assert s0.ids["TD-DOC-4"] in str(cited), cited


@pytest.mark.skip(reason="실모델이 필요하다. 온프레미스 모델 선정 뒤 5174 에서 본다")
def test_UC_060_S05b_실모델_유도(target, s0):
    """「15건이라던데」 유도 (AC-060-10)."""


@pytest.mark.skip(reason="실모델이 필요하다")
def test_UC_060_S07_지연_작업과_사유(target, s0):
    """지연 작업 3.2 와 사유 근거 (AC-060-1·2)."""


@pytest.mark.skip(reason="온프레미스 모델·인터넷 차단 환경이 필요하다(IM-005 8절 INST-S09)")
def test_UC_060_S09_폐쇄망_모델(target, s0):
    """폐쇄망 모델로 S01~S03·S07 (AC-060-8)."""


@pytest.mark.skip(reason="DEC-11(이행률 분모·AI 범위) 결정 전")
def test_UC_060_S11_요구사항_목록(target, s0):
    """요구사항 목록 A·B·D, C 구분 (A5)."""


# ------------------------------------------------------------------ UC-061


def test_UC_061_S02_거절들(target, s0):
    """임베딩 모델 선택 / 없는 모델 / 비관리자 조회 → 거절 (AC-061-1·2)."""
    assert target.get("/api/ai/settings", headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 403
    assert target.get("/api/ai/settings", headers=auth(s0.tokens["TD-ACC-V1"])).status_code == 403
    adm = auth(s0.tokens["TD-ACC-A1"])
    assert target.get("/api/ai/settings", headers=adm).status_code == 200
    base = target.get("/api/ai/settings", headers=adm).json().get("baseUrl") or "http://localhost:11434"
    res = target.put("/api/ai/settings", json={"baseUrl": base, "model": "bge-m3"}, headers=adm)
    assert res.status_code in (400, 409, 422), res.text
    res = target.put("/api/ai/settings", json={"baseUrl": base, "model": "없는-모델:0b"}, headers=adm)
    assert res.status_code in (400, 404, 409, 422, 502), res.text
    assert target.put("/api/ai/settings", json={"baseUrl": base, "model": "x"}, headers=auth(s0.tokens["TD-ACC-C1"])).status_code == 403


def _llm_setting_row():
    with tx() as cur:
        return fetch_one(cur, "select base_url, model, updated_by_user_id, updated_at from llm_setting where id = 1")


def _restore_llm_setting(before) -> None:
    with tx() as cur:
        if before is None:
            cur.execute("delete from llm_setting where id = 1")
        else:
            cur.execute(
                "insert into llm_setting (id, base_url, model, updated_by_user_id, updated_at) values (1, %s, %s, %s, %s) "
                "on conflict (id) do update set base_url = excluded.base_url, model = excluded.model, "
                "updated_by_user_id = excluded.updated_by_user_id, updated_at = excluded.updated_at",
                (before["base_url"], before["model"], before["updated_by_user_id"], before["updated_at"]),
            )


def test_UC_061_S01_모델_선택(target, s0, screen):
    """새로 고침 → 생성 모델 선택·저장 → 질의 배지 (AC-061-2·5).

    모델 서버가 있는 원격 대상(5174, 공유 axlink-ollama)에서 목록·저장·배지를 본다. 생성 확인 실패
    (E3)는 재생 서버의 Ollama 흉내를 장애로 두고 본다. 프로세스 안(CI)은 고정 응답 모드라 질의 배지가
    「고정 응답(시험용)」 경고를 내는 근거(runtime.fixed)만 본다."""
    c1 = auth(s0.tokens["TD-ACC-C1"])
    if not TARGET_URL:
        runtime = target.get("/api/ai/runtime", headers=c1).json()
        assert runtime["fixed"] is True, runtime
        return
    adm = auth(s0.tokens["TD-ACC-A1"])
    before = _llm_setting_row()
    start = target.get("/api/ai/settings", headers=adm).json()
    try:
        base = start["baseUrl"]
        listed = target.post("/api/ai/models/refresh", params={"baseUrl": base}, headers=adm).json()
        assert not listed.get("error"), listed
        answer = [m["name"] for m in listed["models"] if m["purpose"] == "ANSWER"]
        assert answer, listed
        chosen = start["model"] if start["model"] in answer else answer[0]

        # E3: 생성 확인이 실패하면 저장하지 않고 설정도 그대로다
        replay = os.environ["AXLINK_REPLAY_URL"].rstrip("/")
        inner = (os.environ.get("AXLINK_REPLAY_TARGET_URL") or replay).rstrip("/") + "/ollama"
        RemoteScriptedLlm(replay).script(None, "", fail=True)
        flaky = target.post("/api/ai/models/refresh", params={"baseUrl": inner}, headers=adm).json()
        assert replay_ollama.MODEL in [m["name"] for m in flaky["models"]], flaky
        res = target.put("/api/ai/settings", json={"baseUrl": inner, "model": replay_ollama.MODEL}, headers=adm)
        assert res.status_code == 400 and res.json()["code"] == "MODEL_CHECK_FAILED", res.text
        after = target.get("/api/ai/settings", headers=adm).json()
        assert (after["baseUrl"], after["model"]) == (start["baseUrl"], start["model"]), after

        # 저장: DB 설정이 되고 질의 화면 배지가 그 모델을 보인다
        res = target.put("/api/ai/settings", json={"baseUrl": base, "model": chosen}, headers=adm)
        assert res.status_code == 200, res.text
        saved = res.json()
        assert saved["model"] == chosen and saved["source"] == "DB", saved
        runtime = target.get("/api/ai/runtime", headers=c1).json()
        assert runtime["model"] == chosen and runtime["fixed"] is False, runtime
        if screen:
            sc = screen("TD-ACC-C1")
            sc.open(f"/p/{s0.ids['TD-PRJ-1']}/ask").see(f"답변 모델 {chosen}", selector="body")
            sc.not_see("고정 응답", selector="body")
            sc.done()
    finally:
        _restore_llm_setting(before)


@pytest.mark.remote_llm
def test_UC_061_S03_불일치(target, s0, llm):
    """모의 모델: 장애·오류 처리 검증(검색 멈춤). 임베딩 모델·차원 불일치 표시, 질의는 집계만 (AC-061-3).

    변형: 시험 DB 에 다른 임베딩 모델 이름의 조각 하나를 넣는다(끝에 지운다). 그동안 검색·색인이
    멈추므로 이 시나리오 안에서만 둔다."""
    pid = s0.ids["TD-PRJ-1"]
    other = "other-embed:test"
    vec = "[" + ",".join(["0.01"] * 1024) + "]"
    with tx() as cur:
        issue = fetch_one(cur, "select id from issue where project_id = %s order by id limit 1", (pid,))
        row = fetch_one(
            cur,
            "insert into doc_chunk (project_id, source_type, source_id, chunk_index, content, embedding, embedding_model, "
            "source_title, source_uri, content_hash) values (%s, 'ISSUE', %s, 9999, '불일치 시험 조각', %s::vector, %s, "
            "'불일치 시험', 'test://mismatch', repeat('0', 64)) returning id",
            (pid, issue["id"], vec, other),
        )
    try:
        status = target.get("/api/ai/embedding", headers=auth(s0.tokens["TD-ACC-A1"])).json()
        assert status["consistent"] is False, status
        assert other in (status["message"] or "") and other in [m["model"] for m in status["indexModels"]], status

        # 집계 질문: 문서 검색 없이 집계로 답한다
        llm({"route": "AGGREGATE", "measure": "issue_count", "dimensions": [], "template": "STAT_CARD", "title": "이슈 건수", "query": "이슈 건수"}, "일반 이슈 건수를 알려 드립니다.")
        events = _ask(target, s0, "TD-ACC-C1", "일반 이슈가 몇 건인지 알려줘", [pid])
        assert events[0][1]["routing"]["type"] != "DOCUMENT", events[0][1]
        assert events[0][1]["retrievedChunkCount"] == 0 and _sources(events) == [], events[0][1]
        assert _done(events)["finishReason"] == "STOP", _done(events)
        # 문서 질문: 검색이 멈췄다고 안내한다
        llm({"route": "DOCUMENT", "query": "사업 기간"}, "지어낸 답")
        events = _ask(target, s0, "TD-ACC-C1", "사업 기간은 몇 개월인가", [pid])
        assert _done(events)["finishReason"] == "SEARCH_DISABLED", _done(events)
        assert "지어낸 답" not in _text(events) and _sources(events) == [], _text(events)
    finally:
        with tx() as cur:
            cur.execute("delete from doc_chunk where id = %s", (row["id"],))


@pytest.mark.skipif(not TARGET_URL, reason="클라우드 위임 모델이 든 모델 서버 목록이 필요하다. 5174 에서 본다(구분 규칙은 tests/test_llm_settings.py)")
def test_UC_061_S04_클라우드_표시(target, s0):
    """새로 고침 → 클라우드 위임 모델이 목록에서 구분된다 (AC-061-4).

    원격 대상의 모델 서버(5174 공유 axlink-ollama) 목록에 클라우드 위임 모델(gemma4:31b-cloud)과
    로컬 모델이 같이 있다. 목록 조회만 하고 설정은 바꾸지 않는다."""
    adm = auth(s0.tokens["TD-ACC-A1"])
    base = target.get("/api/ai/settings", headers=adm).json()["baseUrl"]
    listed = target.post("/api/ai/models/refresh", params={"baseUrl": base}, headers=adm).json()
    assert not listed.get("error"), listed
    cloud = [m for m in listed["models"] if m.get("cloud")]
    local = [m for m in listed["models"] if not m.get("cloud")]
    assert cloud, f"클라우드 위임 모델이 구분되지 않았다: {[(m['name'], m.get('cloud')) for m in listed['models']]}"
    assert all(m["remoteHost"] for m in cloud), cloud
    assert local and all(m["remoteHost"] is None for m in local), local


# ------------------------------------------------------------------ UC-070


def _upload(target, s0, prj: str, content: bytes, name: str, mime: str, acc="TD-ACC-V1"):
    """올리고 처리가 끝날 때까지 기다린다. 원격 서버는 처리를 뒤에서 한다."""
    res = target.post(f"/api/projects/{s0.ids[prj]}/documents", files={"file": (name, content, mime)}, headers=auth(s0.tokens[acc]))
    if res.status_code in (200, 201, 202):
        s0.await_document(acc, res.json()["id"])
    return res


def test_UC_070_S03_형식_크기_거절(target, s0):
    """.zip / 빈 파일 → 각각 거절, 사유 (AC-070-1). 상한 초과(TD-DOC-11)는 자료 없음."""
    res = _upload(target, s0, "TD-PRJ-9", b"PK\x03\x04zip", "자료.zip", "application/zip")
    assert res.status_code == 400, res.text
    assert res.json().get("message")
    res = _upload(target, s0, "TD-PRJ-9", b"", "빈파일.docx", DOCX)
    assert res.status_code == 400, res.text


def test_UC_070_S04_손상_파일(target, s0):
    """손상 DOCX → 실패 「본문 읽기 실패」 (AC-070-5)."""
    res = _upload(target, s0, "TD-PRJ-9", b"\x00\x01broken-not-a-zip" * 50, "손상파일.docx", DOCX)
    assert res.status_code in (200, 201, 202), res.text
    doc = target.get(f"/api/documents/{res.json()['id']}", headers=auth(s0.tokens["TD-ACC-V1"])).json()
    assert doc["status"] == "FAILED", doc
    # 명세 문안은 「본문 읽기 실패」. 제품 문안 「파일이 손상됐거나 형식이 확장자와 다릅니다」도 같은 뜻으로 본다
    assert doc["error"] and any(k in doc["error"] for k in ("읽", "본문", "손상")), doc["error"]


def test_UC_070_S02_XLSX_표_행_번호(target, s0):
    """TD-DOC-6 사본 → 시트 「WBS」 표 열 구조, 원본 행 번호(2~7) (AC-070-2·8)."""
    res = _upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-6"].read_bytes(), "WBS-사본.xlsx", XLSX)
    assert res.status_code in (200, 201, 202), res.text
    did = res.json()["id"]
    text = target.get(f"/api/documents/{did}/text", headers=auth(s0.tokens["TD-ACC-V1"])).json()["text"]
    assert "WBS" in text and "요구사항정의서" in text and "|" in text, text[:300]
    chunks = target.get(f"/api/documents/{did}/chunks?size=50", headers=auth(s0.tokens["TD-ACC-V1"])).json()
    joined = json.dumps(chunks, ensure_ascii=False)
    assert "행" in joined or "row" in joined.lower(), "청크 위치에 원본 행 번호가 없다"


def test_UC_070_S09_DOCX_표(target, s0):
    """TD-DOC-2 사본 → 표 「요구사항 목록」 3행 × 열 보존, 2절 문단 (AC-070-8)."""
    res = _upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-2"].read_bytes(), "요구사항정의서-사본.docx", DOCX)
    assert res.status_code in (200, 201, 202), res.text
    text = target.get(f"/api/documents/{res.json()['id']}/text", headers=auth(s0.tokens["TD-ACC-V1"])).json()["text"]
    rows = [ln for ln in text.splitlines() if ln.startswith("|") and "UR.PORT" in ln]
    assert len(rows) == 3, rows
    assert all(ln.count("|") >= 4 for ln in rows), rows
    assert "요구사항은 총 3건이다" in text


def test_UC_070_S12_XLSX_가변_머리글(target, s0):
    """TD-DOC-14 → 머리글 4행 인식, 자료 5건, 1~3행 집계 블록은 본문으로 보존 (AC-070-9)."""
    res = _upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-14"].read_bytes(), "위험관리대장.xlsx", XLSX)
    assert res.status_code in (200, 201, 202), res.text
    text = target.get(f"/api/documents/{res.json()['id']}/text", headers=auth(s0.tokens["TD-ACC-V1"])).json()["text"]
    assert "총 5건" in text, text[:200]
    rows = [ln for ln in text.splitlines() if ln.startswith("|") and ("높음" in ln or "중간" in ln or "낮음" in ln)]
    assert len(rows) == 5, rows
    header = [ln for ln in text.splitlines() if ln.startswith("|") and "위험" in ln and "심각도" in ln]
    assert header, "머리글 행(번호·위험·심각도·상태·담당)을 찾지 못했다"


def test_UC_070_S08_다른_사업(target, s0):
    """V3 가 TD-PRJ-1 에 올리기 → 거절 (COMMON-S01)."""
    res = _upload(target, s0, "TD-PRJ-1", s0.files["TD-DOC-5"].read_bytes(), "회의록.docx", DOCX, acc="TD-ACC-V3")
    assert res.status_code == 403, res.text


def _docx_bytes(marker: str) -> bytes:
    import io

    from docx import Document

    doc = Document()
    doc.add_paragraph(f"자료 화면 시험 {marker}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_UC_070_S14_자료_목록과_검색(target, s0, screen):
    """작업(3.5)에 올린 산출물은 자료 목록에 나오지 않고 기타 자료만 나온다. 파일명 검색은 %·_ 를 글자 그대로
    찾는다. 자료 상세에는 WBS 연결·유형 수정·산출물 제출 조작이 없다 (AC-070-11)."""
    pid = s0.ids["TD-PRJ-1"]
    v1 = auth(s0.tokens["TD-ACC-V1"])
    made: list[str] = []
    try:
        task = target.post(
            f"/api/projects/{pid}/documents",
            files={"file": ("사용자매뉴얼-S14.docx", _docx_bytes("작업"), DOCX)}, data={"wbsId": "3.5"}, headers=v1,
        )
        assert task.status_code == 201, task.text
        made.append(task.json()["id"])
        s0.await_document("TD-ACC-V1", made[-1])
        for name in ("회의록_100%.docx", "회의록 1100.docx", "착수 회의 메모.docx"):
            res = _upload(target, s0, "TD-PRJ-1", _docx_bytes(name), name, DOCX)
            assert res.status_code == 201, res.text
            made.append(res.json()["id"])

        def names(q: str | None = None) -> set[str]:
            url = f"/api/projects/{pid}/documents?general=true&size=100" + (f"&q={q}" if q else "")
            res = target.get(url, headers=v1)
            assert res.status_code == 200, res.text
            body = res.json()
            return {x["fileName"] for x in (body.get("content") or body.get("items") or [])}

        listed = names()
        assert "사용자매뉴얼-S14.docx" not in listed, "작업에 올린 산출물이 자료 목록에 나왔다"
        assert {"회의록_100%.docx", "회의록 1100.docx", "착수 회의 메모.docx"} <= listed
        from urllib.parse import quote

        assert names(quote("_1")) == {"회의록_100%.docx"}, names(quote("_1"))
        assert names(quote("0%")) == {"회의록_100%.docx"}, names(quote("0%"))
        assert names(quote("회의록")) >= {"회의록_100%.docx", "회의록 1100.docx"}
        if screen:
            sc = screen("TD-ACC-V1")
            sc.open(f"/p/{pid}/documents").see("회의록_100%.docx")
            assert "사용자매뉴얼-S14.docx" not in sc.page.locator("main").inner_text()
            sc.page.get_by_label("파일명 검색").fill("_1")
            sc.page.wait_for_timeout(800)
            body = sc.page.locator("main").inner_text()
            assert "회의록_100%.docx" in body and "회의록 1100.docx" not in body, body[:400]
            sc.shot("자료 검색")
            sc.open(f"/p/{pid}/documents/{made[1]}").see("회의록_100%.docx")
            body = sc.page.locator("main").inner_text()
            for word in ("WBS 연결", "유형 수정", "산출물로 제출"):
                assert word not in body, f"자료 상세에 「{word}」 조작이 남아 있다"
            sc.shot("자료 상세")
            sc.done()
    finally:
        for doc in made:
            target.delete(f"/api/documents/{doc}", headers=v1)


def test_UC_070_S06_삭제(target, s0):
    """TD-DOC-2(산출물 v1 승인) 삭제 → 색인 0, 산출물 v1 기록 유지 (AC-070-6)."""
    did = s0.ids["TD-DOC-2"]
    pid = s0.ids["TD-PRJ-1"]
    res = target.delete(f"/api/documents/{did}", headers=auth(s0.tokens["TD-ACC-V1"]))
    assert res.status_code == 204, res.text
    with tx() as cur:
        chunks = fetch_one(cur, "select count(*) as n from doc_chunk where source_id = %s", (did,))["n"]
        wp = fetch_one(cur, "select version, status from work_product where project_id = %s and type = 'REQUIREMENTS_SPEC' and is_current", (pid,))
    assert chunks == 0
    assert wp is not None and wp["version"] == "v1" and wp["status"] == "APPROVED", wp


def test_UC_070_S01_PDF_업로드_처리(target, s0, screen):
    """TD-DOC-4(PDF 3쪽) 올리기 → 완료, 쪽 수 3, 2쪽 「22종」·3쪽 「9개월」, 청크 위치에 쪽 (AC-070-2·3·8).

    올리기는 S0 투입(V1)이 했다. 접수 → 처리 → 완료 흐름은 투입의 await_document 가 거쳤다."""
    did = s0.ids["TD-DOC-4"]
    doc = target.get(f"/api/documents/{did}", headers=auth(s0.tokens["TD-ACC-V1"])).json()
    assert doc["processingState"] == "DONE" and doc["status"] != "FAILED", doc
    assert doc["pageCount"] == 3, doc["pageCount"]
    with tx() as cur:
        rows = fetch_all(
            cur,
            "select content, (meta_json->>'page')::int as page from doc_chunk "
            "where source_id = %s order by chunk_index",
            (did,),
        )
    pages = {r["page"] for r in rows}
    assert {2, 3} <= pages, rows
    assert any("22종" in r["content"] and r["page"] == 2 for r in rows), rows
    assert any("9개월" in r["content"] and r["page"] == 3 for r in rows), rows
    if screen:
        sc = screen("TD-ACC-V1")
        sc.open(f"/p/{s0.ids['TD-PRJ-1']}/documents/{did}").see("과업지시서.pdf", "납품 산출물은 22종이다", "사업 기간은 9개월이다")
        sc.done()


HWP = "application/x-hwp"
HWPX = "application/hwp+zip"
# TD-DOC-12·13 의 내용(tests/fixtures/im009/hwp/make_hwp.ps1). 표 3행 × 4열 = 머리글 1행 + 자료 2행
HWP_TABLE_ROWS = (
    ("항목", "검토자", "결과", "비고"),
    ("외부 연계 규격", "김주무관", "보완", "응답 코드 표 추가"),
    ("화면 설계", "박피엠", "적합", "없음"),
)
HWP_PARAGRAPHS = (
    "회의 일시는 2026년 8월 25일 14시이고 장소는 가람시 정보화원 회의실이다.",
    "검토 대상은 SW설계서 v0.9 이며 외부 연계 규격을 중심으로 검토했다.",
    "결론: 지적 사항 2건을 반영해 SW설계서 v1.0 으로 다시 제출한다.",
)


def _hwp_case(target, s0, tid: str, name: str, mime: str) -> None:
    """표 3행×4열 보존(항목·검토자·결과·비고), 문단 3개, 출처 위치는 문단·표·행 (UC-070-S10·S11).

    HWP·HWPX 파일에는 쪽 나눔 정보가 없다. 쪽 수·쪽 위치를 만들지 않고 실제 확보한 문단·표·행
    위치를 출처로 낸다(DEC-21)."""
    res = _upload(target, s0, "TD-PRJ-9", s0.files[tid].read_bytes(), name, mime)
    assert res.status_code in (200, 201, 202), res.text
    did = res.json()["id"]
    v1 = auth(s0.tokens["TD-ACC-V1"])
    doc = target.get(f"/api/documents/{did}", headers=v1).json()
    assert doc["processingState"] == "DONE" and doc["status"] != "FAILED", doc
    text = target.get(f"/api/documents/{did}/text", headers=v1).json()["text"]
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in text.splitlines() if ln.startswith("|") and "---" not in ln]
    assert [tuple(r) for r in rows] == list(HWP_TABLE_ROWS), rows
    missing = [p for p in HWP_PARAGRAPHS if p not in text]
    assert not missing, (missing, text[:400])
    assert doc["pageCount"] is None, f"없는 쪽 수를 냈다: {doc['pageCount']}"
    with tx() as cur:
        rows = fetch_all(
            cur,
            "select c.id::text as id, c.project_id::text as project_id, p.name as project_name, "
            "c.source_type, c.source_id::text as source_id, c.source_title, c.source_uri, "
            "c.chunk_index, c.content, c.meta_json, 1.0 as similarity "
            "from doc_chunk c join project p on p.id = c.project_id "
            "where c.source_id = %s order by c.chunk_index",
            (did,),
        )
    assert rows, "색인 조각이 없다"
    # 문서 질의 출처 카드에 붙는 위치 문구를 제품 함수 그대로 만든다
    locations = [ask_answer.location_text(ask_search._chunk(r, 0.0)) for r in rows]
    assert not any("p." in (loc or "") for loc in locations), locations
    # 문단 5개(머리 표기·제목·본문 3) 와 표 1개 3행이 한 조각에 든다
    assert locations == ["문단 1~5 / 표 1 · 1~3행"], locations


def test_UC_070_S10_HWP_표(target, s0):
    """TD-DOC-12(HWP 5.0) → 표 3행×4열(항목·검토자·결과·비고), 문단 3개, 출처 「문단 1~5 / 표 1 · 1~3행」 (AC-070-8)."""
    _hwp_case(target, s0, "TD-DOC-12", "설계검토회의록.hwp", HWP)


def test_UC_070_S11_HWPX_표(target, s0):
    """TD-DOC-13(HWPX) → TD-DOC-12 와 같은 표·문단 (AC-070-8)."""
    _hwp_case(target, s0, "TD-DOC-13", "설계검토회의록.hwpx", HWPX)


def test_UC_070_S13_지원_제한_구분(target, s0):
    """TD-DOC-15(암호 HWP)·TD-DOC-16(스캔 PDF) → 둘 다 「처리 실패: 지원 제한(암호/스캔)」.
    TD-DOC-15 를 HWPX 로 변환한 판(TD-DOC-13 과 같은 내용)을 다시 올리면 정상 (AC-070-10·5).

    변환본 재업로드는 대응 절차다. HWP 5.0 정상 지원의 근거(UC-070-S10)로 세지 않는다."""
    v1 = auth(s0.tokens["TD-ACC-V1"])
    for tid, name, mime, kind in (
        ("TD-DOC-15", "암호문서.hwp", HWP, "암호"),
        ("TD-DOC-16", "스캔문서.pdf", "application/pdf", "스캔"),
    ):
        res = _upload(target, s0, "TD-PRJ-9", s0.files[tid].read_bytes(), name, mime)
        assert res.status_code in (200, 201, 202), res.text
        doc = target.get(f"/api/documents/{res.json()['id']}", headers=v1).json()
        assert doc["processingState"] == "FAILED", (tid, doc)
        reason = doc.get("processingError") or ""
        # 손상 파일의 「본문 읽기 실패」(UC-070-S04)·색인 장애의 「색인 실패」(UC-070-S05)와 구분된다
        assert reason.startswith(f"지원 제한({kind})"), (tid, reason)
    res = _upload(target, s0, "TD-PRJ-9", s0.files["TD-DOC-13"].read_bytes(), "암호문서.hwpx", HWPX)
    assert res.status_code in (200, 201, 202), res.text
    doc = target.get(f"/api/documents/{res.json()['id']}", headers=v1).json()
    assert doc["processingState"] == "DONE" and doc["status"] != "FAILED", doc


# ---- 5174 전용 장애 주입 (UC-070-S05·S07) ----------------------------------------------
# 원격에서는 5174 API 의 임베딩 주소를 재생 서버의 임베딩 중계로 돌려 둔 실행에서만 돈다
# (AXLINK_VERIFY_EMBED_PROXY=1). 공유 모델 서버는 멈추지 않는다(tests/fixtures/im009/embed_proxy.py).
# 재시작은 AXLINK_VERIFY_RESTART 에 적은 5174 API 컨테이너 하나만, 대상이 5174 일 때만 한다.
RESTART_CONTAINER = "axlink-int-api"


def _remote_injection(*, restart: bool = False) -> None:
    if not TARGET_URL:
        return
    if os.environ.get("AXLINK_VERIFY_EMBED_PROXY") != "1" or not os.environ.get("AXLINK_REPLAY_URL"):
        pytest.skip("5174 임베딩 중계가 설정되지 않았다(AXLINK_VERIFY_EMBED_PROXY·AXLINK_REPLAY_URL)")
    if restart:
        if os.environ.get("AXLINK_VERIFY_RESTART") != RESTART_CONTAINER:
            pytest.skip(f"재시작 주입이 허용되지 않았다(AXLINK_VERIFY_RESTART={RESTART_CONTAINER})")
        if not re.search(r"//(127\.0\.0\.1|localhost):5174/", TARGET_URL + "/"):
            pytest.skip(f"재시작 주입은 5174 대상에서만 한다: {TARGET_URL}")


def _embed(mode: str | None = None) -> dict:
    """원격 임베딩 중계 상태. mode 를 주면 바꾼다."""
    base = os.environ["AXLINK_REPLAY_URL"].rstrip("/")
    with httpx.Client(timeout=10) as c:
        res = c.put(f"{base}/_replay/embed", json={"mode": mode}) if mode else c.get(f"{base}/_replay/embed")
    res.raise_for_status()
    return res.json()


def _wait(cond, what: str, timeout: float = 90.0, every: float = 0.5):
    deadline = time.monotonic() + timeout
    while True:
        got = cond()
        if got:
            return got
        if time.monotonic() > deadline:
            raise AssertionError(f"{timeout:.0f}초 안에 {what} 되지 않았다")
        time.sleep(every)


def _doc_row(did: str) -> dict:
    with tx() as cur:
        return fetch_one(cur, "select processing_state, processing_attempts, processing_error from document_upload where id = %s", (did,))


def _post_doc(target, s0, prj: str, content: bytes, name: str, mime: str, acc="TD-ACC-V1") -> str:
    """올리기만 한다(처리를 기다리지 않는다)."""
    res = target.post(f"/api/projects/{s0.ids[prj]}/documents", files={"file": (name, content, mime)}, headers=auth(s0.tokens[acc]))
    assert res.status_code in (200, 201, 202), res.text
    return res.json()["id"]


def _unique_docx(tag: str) -> bytes:
    """내용이 실행마다 다른 DOCX(같은 해시로 기존 문서에 묶이지 않게)."""
    from docx import Document

    doc = Document()
    doc.add_heading(f"재시작 시험 문서 {tag}", level=1)
    for i in range(1, 6):
        doc.add_paragraph(f"{i}. 민원 처리 현황 주간 점검 기록 {tag}-{i}. 처리 기한을 넘긴 민원은 담당 부서에 알린다.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class _DownEmbedding:
    """임베딩 서버가 멈춘 것과 같은 꼴(실제 어댑터가 재시도 뒤 내는 오류)."""

    def model_name(self) -> str:
        return settings.embedding_model

    def dimension(self) -> int:
        return settings.embedding_dimension

    def embed(self, texts):
        raise errors.ApiError(503, "AI_UNAVAILABLE", "임베딩 모델에 닿지 못했습니다: 시험 주입(서버 중단)")


def test_UC_070_S05_색인_장애_뒤_재처리(target, s0, monkeypatch):
    """임베딩 서버 중단 중 TD-DOC-5 올리기 → 「색인 실패」 → 복구 → 같은 파일 재업로드 → 같은 문서 ID 로 완료 (AC-070-4·5)."""
    from app.document import service as doc_service

    _remote_injection()
    content = s0.files["TD-DOC-5"].read_bytes()
    v1 = auth(s0.tokens["TD-ACC-V1"])
    try:
        if TARGET_URL:
            _embed("down")
        else:
            monkeypatch.setattr(doc_service, "embedding_port", lambda: _DownEmbedding())
        res = _upload(target, s0, "TD-PRJ-9", content, "회의록_2026-08-25.docx", DOCX)
        assert res.status_code in (200, 201, 202), res.text
        did = res.json()["id"]
        doc = target.get(f"/api/documents/{did}", headers=v1).json()
        assert doc["processingState"] == "FAILED", doc
        # 색인 장애는 「색인 실패」로, 손상 파일의 「본문 읽기 실패」(UC-070-S04)와 구분된다(AC-070-5)
        assert (doc.get("processingError") or "").startswith("색인 실패"), doc
    finally:
        if TARGET_URL:
            _embed("pass")
        else:
            monkeypatch.undo()
    res = _upload(target, s0, "TD-PRJ-9", content, "회의록_2026-08-25.docx", DOCX)
    assert res.status_code in (200, 201, 202), res.text
    assert res.json()["id"] == did, "같은 파일 재업로드가 새 문서가 됐다(AC-070-4)"
    doc = target.get(f"/api/documents/{did}", headers=v1).json()
    assert doc["processingState"] == "DONE" and not doc.get("processingError"), doc
    with tx() as cur:
        n = fetch_one(cur, "select count(*) as n from doc_chunk where source_id = %s", (did,))["n"]
    assert n > 0, "재처리 뒤 색인 조각이 없다"


def _restart_api(target) -> None:
    """5174 API 컨테이너 하나만 다시 시작하고 응답할 때까지 기다린다."""
    subprocess.run(["docker", "restart", RESTART_CONTAINER], check=True, capture_output=True, timeout=180)

    def up() -> bool:
        try:
            return target.get("/api/health").status_code == 200
        except httpx.HTTPError:
            return False

    _wait(up, "API 가 다시 응답", timeout=240, every=2)


def test_UC_070_S07_재시작(target, s0, monkeypatch):
    """처리 중 작업자 재시작 → 대기열 복귀 → 완료. 같은 작업이 3회 끊기면 사유와 함께 실패 (AC-070-7).

    원격: 임베딩 중계가 색인 요청을 붙잡은 사이 5174 API 를 실제로 다시 시작한다. 기동 정리가
    처리 중이던 작업을 대기열에 다시 넣고, 같은 작업이 3번 끊기면 실패로 남긴다.
    프로세스 안: 처리를 끊긴 채(처리 중) 두고 기동 정리(recover)를 부른다. 같은 저장소 SQL 이다."""
    from app.document import repository as doc_repo
    from app.document import service as doc_service

    _remote_injection(restart=True)
    tag = uuid.uuid4().hex[:8]
    ok_bytes, fail_bytes = _unique_docx(f"{tag}-A"), _unique_docx(f"{tag}-B")
    max_attempts = 3  # 명세(UC-070-S07) 「3회 반복 시 실패」. 제품 설정 document_max_attempts 기본값과 같다
    v1 = auth(s0.tokens["TD-ACC-V1"])

    if not TARGET_URL:
        assert settings.document_max_attempts == max_attempts
        real_run = doc_service.run_job
        monkeypatch.setattr(doc_service, "run_job", lambda job, txf: None)  # 처리 중에 끊긴 것처럼 둔다

        def restart() -> None:
            doc_service.recover(True)  # 기동 정리

        def reclaim() -> None:
            with tx() as cur:
                assert doc_repo.claim_next(cur) is not None  # 작업자가 다시 가져가 처리 중

        ok = _post_doc(target, s0, "TD-PRJ-9", ok_bytes, f"재시작-완료-{tag}.docx", DOCX)
        assert _doc_row(ok)["processing_state"] == "RUNNING"
        restart()
        assert _doc_row(ok)["processing_state"] == "QUEUED", "재시작 뒤 대기열로 돌아가지 않았다"
        monkeypatch.setattr(doc_service, "run_job", real_run)
        assert doc_service.process_next()
        row = _doc_row(ok)
        assert row["processing_state"] == "DONE" and row["processing_attempts"] == 2, row

        monkeypatch.setattr(doc_service, "run_job", lambda job, txf: None)
        bad = _post_doc(target, s0, "TD-PRJ-9", fail_bytes, f"재시작-실패-{tag}.docx", DOCX)
        for i in range(1, max_attempts + 1):
            restart()
            if i < max_attempts:
                assert _doc_row(bad)["processing_state"] == "QUEUED", (i, _doc_row(bad))
                reclaim()
        monkeypatch.setattr(doc_service, "run_job", real_run)
    else:
        try:
            # 1) 한 번 끊김 → 대기열 복귀 → 완료
            _embed("hold")
            calls = _embed()["calls"]
            ok = _post_doc(target, s0, "TD-PRJ-9", ok_bytes, f"재시작-완료-{tag}.docx", DOCX)
            _wait(lambda: _embed()["calls"] > calls and _doc_row(ok)["processing_state"] == "RUNNING", "처리 중(색인 대기)")
            calls = _embed()["calls"]
            _restart_api(target)
            _wait(lambda: _embed()["calls"] > calls, "재시작 뒤 같은 작업을 다시 처리", timeout=120)
            assert _doc_row(ok)["processing_state"] == "RUNNING"
            _embed("pass")
            done = s0.await_document("TD-ACC-V1", ok)
            row = _doc_row(ok)
            assert done["processingState"] == "DONE" and row["processing_attempts"] == 2, (done, row)

            # 2) 같은 작업이 3번 끊김 → 실패와 사유
            _embed("hold")
            calls = _embed()["calls"]
            bad = _post_doc(target, s0, "TD-PRJ-9", fail_bytes, f"재시작-실패-{tag}.docx", DOCX)
            for i in range(1, max_attempts + 1):
                _wait(lambda n=calls: _embed()["calls"] > n and _doc_row(bad)["processing_state"] == "RUNNING", f"{i}번째 처리 중", timeout=120)
                calls = _embed()["calls"]
                _restart_api(target)
            s0.await_document("TD-ACC-V1", bad, timeout=60)
        finally:
            _embed("pass")

    doc = target.get(f"/api/documents/{bad}", headers=v1).json()
    row = _doc_row(bad)
    assert row["processing_state"] == "FAILED" and row["processing_attempts"] == max_attempts, row
    reason = doc.get("processingError") or ""
    assert f"{max_attempts}번 중단" in reason and "재시작" in reason, reason


def _ui_UC_060_S06a(screen, s0):
    """화면: C2·V3 의 사업 목록에 TD-PRJ-1 이 없고, 그 사업 질의 화면 주소는 권한 없음."""
    if not screen:
        return
    from tests.fixtures.im009 import data as d

    for acc in ("TD-ACC-C2", "TD-ACC-V3"):
        sc = screen(acc).expect_denied()
        sc.open("/projects").see("사업 목록")
        sc.not_see(d.PROJECTS["TD-PRJ-1"].name)
        sc.open(f"/p/{s0.ids['TD-PRJ-1']}/ask").see("접근 권한이 없습니다", selector="body")
        assert sc.denied, f"{acc}: 화면만 막고 서버가 거절하지 않았다"
        sc.done()
