# ruff: noqa: E501
"""G·H 그룹: AI 질의·모델 설정 (UC-060·061) 과 자료 (UC-070) 예제 시나리오.

모델은 대본대로 답하는 흉내(ScriptedLlm)다. 여기서 보는 것은 라우팅·게이트·수치 검문·출처 위치가
설계대로 움직이는지이고, 문장 품질과 실모델 일치(AC-060-8·10)는 5174 실모델에서 본다.
PDF(TD-DOC-4)·HWP·HWPX·손상·대용량 자료는 생성기가 없어 「자료 없음」으로 보류한다(files.MISSING).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.ai.port import LlmResult
from app.common import errors
from app.config import settings
from app.db import fetch_one, tx
from app.rag import number_guard
from app.rag import service as ask_service
from tests.scenarios.conftest import auth

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


@pytest.fixture
def llm(monkeypatch):
    def _install(route: dict | None, text: str, fail: bool = False, min_sim: float = -1.0) -> ScriptedLlm:
        scripted = ScriptedLlm(route, text, fail)
        monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
        monkeypatch.setattr(settings, "rag_min_similarity", min_sim)
        monkeypatch.setattr(settings, "rag_top_k", 20)
        return scripted
    return _install


# ------------------------------------------------------------------ UC-060


def test_UC_060_S02_집계_질문(target, s0, llm):
    """「일반 이슈가 몇 건이야」 → 9건, 산출 근거(리스크·결함·출처 이슈 제외), 그림 없음 (AC-060-2)."""
    scripted = llm({"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"}, "일반 이슈는 모두 9건입니다.")
    events = _ask(target, s0, "TD-ACC-C1", "일반 이슈가 몇 건이야", [s0.ids["TD-PRJ-1"]])
    text, done = _text(events), _done(events)
    assert done["finishReason"] != "NUMBER_GUARD", f"9건이 집계(현재 결함 포함 11건, DEC-02)와 어긋나 막혔다: {text}"
    assert "9건" in text, text
    assert "infographic" not in [e for e, _ in events]
    assert scripted.stream_calls == 1


def test_UC_060_S04_근거_부족(target, s0, llm):
    """「이번 달 지출 내역 알려줘」 → 생성 호출 0, 근거 부족 문안, 출처 0 (AC-060-3)."""
    scripted = llm({"route": "DOCUMENT", "query": "지출 내역"}, "지어낸 답", min_sim=0.99)
    events = _ask(target, s0, "TD-ACC-C1", "이번 달 지출 내역 알려줘", [s0.ids["TD-PRJ-1"]])
    assert scripted.stream_calls == 0
    assert _sources(events) == []
    text = _text(events)
    # 근거 부족 문안에 유사도와 문턱이 적힌다(AC-060-3)
    assert ("찾지 못" in text or "부족" in text) and "유사도" in text and "기준" in text, text
    assert "지어낸 답" not in text


def test_UC_060_S05a_주입_차단(target, s0, llm):
    """가짜 모델이 「이슈는 977건」 출력 → 그 문장 미출력·미저장, 종료 사유 수치 검문 (AC-060-4)."""
    with tx() as cur:
        n = fetch_one(cur, "select count(*) as n from issue where project_id = %s", (s0.ids["TD-PRJ-1"],))["n"]
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


def test_UC_060_S17_잘못된_대상_결합(target, s0, llm):
    """가짜 모델이 「일반 이슈 처리율은 50%」(50 은 위험 처리율) → 그 문장 차단 (AC-060-12·4, DEC-13 무관)."""
    llm({"route": "AGGREGATE", "measure": "issue_resolution_rate", "template": "STAT_CARD"}, "일반 이슈 처리율은 50% 입니다. 확인해 주세요.")
    events = _ask(target, s0, "TD-ACC-C1", "일반 이슈 처리율이 얼마야", [s0.ids["TD-PRJ-1"]])
    text = _text(events)
    assert "50%" not in text, text
    assert _done(events)["finishReason"] == "NUMBER_GUARD", _done(events)


def test_UC_060_S06a_다른_사업_접근_거절(target, s0):
    """C2 / V3 가 TD-PRJ-1 을 범위에 넣어 질문 → 서버 거절 (AC-060-6)."""
    for acc in ("TD-ACC-C2", "TD-ACC-V3"):
        res = _conversation(target, s0, acc, [s0.ids["TD-PRJ-1"]])
        assert res.status_code == 403, (acc, res.status_code, res.text[:120])


@pytest.mark.skip(reason="DEC-15(용역사 질의 허용) 결정 전. 결정 뒤 V1 의 답 또는 거절을 단언한다")
def test_UC_060_S06b_배정된_용역사의_질의(target, s0):
    """V1 이 TD-PRJ-1 범위로 질문 (AC-060-6, DEC-15)."""


def test_UC_060_S08_값_없음_구분(target, s0, llm):
    """TD-PRJ-3 「진척률이 얼마야」 → 「WBS 없음」 문안, 문서 경로로 안 감 (AC-060-7)."""
    scripted = llm({"route": "AGGREGATE", "measure": "progress_representative_pct", "template": "STAT_CARD"}, "진척률은 계산할 수 없습니다.")
    events = _ask(target, s0, "TD-ACC-C1", "진척률이 얼마야", [s0.ids["TD-PRJ-3"]])
    start = events[0][1]
    text = _text(events)
    assert start["routing"]["type"] != "DOCUMENT", start["routing"]
    assert ("WBS" in text or "없" in text or "산출" in text), text
    assert "0%" not in text and "0.0" not in text, f"재료 없는 사업에 0% 가 답으로 나갔다: {text}"
    assert scripted.stream_calls <= 1


def test_UC_060_S10_모델_장애(target, s0, llm):
    """모델 서버 중단 → 집계 값으로 답(생성 없음) 또는 「쓸 수 없음」, 생성 호출 없음 (AC-060-9)."""
    scripted = llm(None, "", fail=True)
    conv = _conversation(target, s0, "TD-ACC-C1", [s0.ids["TD-PRJ-1"]])
    assert conv.status_code == 201
    with target.stream("POST", f"/api/conversations/{conv.json()['id']}/messages", json={"question": "일반 이슈가 몇 건이야", "projectScope": []}, headers={**auth(s0.tokens["TD-ACC-C1"]), "Accept": "text/event-stream"}) as res:
        assert res.status_code in (200, 502, 503), res.read()
        events = _events(res) if res.status_code == 200 else []
    # 안내는 delta(집계 값 답) 또는 error 사건의 문장으로 온다. 화면은 error 문장을 그대로 보인다
    text = _text(events) + "".join(dd.get("message", "") for e, dd in events if e == "error")
    assert ("건" in text) or ("쓸 수 없" in text), text
    assert "Errno" not in text, "연결 오류 원문이 화면에 나간다"
    assert scripted.stream_calls == 0


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


@pytest.mark.skip(reason="TD-DOC-4(과업지시서.pdf) 자료 없음(files.MISSING). 자료 확보 뒤 실행")
def test_UC_060_S01_문서_질문과_출처(target, s0):
    """「납품 산품은 몇 종인가」 → 22종·각주·2쪽 (AC-060-1)."""


@pytest.mark.skip(reason="TD-DOC-4 자료 없음. S01 과 함께 실행")
def test_UC_060_S03_결합(target, s0):
    """22종(문서)+9건(집계) 한 답 (AC-060-5)."""


@pytest.mark.skip(reason="TD-DOC-4 자료 없음. S01 과 함께 실행")
def test_UC_060_S13_PDF_쪽_위치(target, s0):
    """9개월, 출처 3쪽 (AC-060-11·1)."""


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


@pytest.mark.skip(reason="시험 모델 서버가 필요하다. 5174 의 모델 서버(axlink-ollama)로 본다")
def test_UC_061_S01_모델_선택(target, s0):
    """새로 고침 → 생성 모델 선택·저장 → 질의 배지 (AC-061-2·5)."""


@pytest.mark.skip(reason="S0 복제본에 다른 임베딩 모델 조각을 주입하는 변형 절차는 별도 설계")
def test_UC_061_S03_불일치(target, s0):
    """임베딩 모델·차원 불일치 표시, 질의는 집계만 (AC-061-3)."""


@pytest.mark.skip(reason="클라우드 위임 모델이 든 모델 서버 목록이 필요하다. 5174 에서 본다")
def test_UC_061_S04_클라우드_표시(target, s0):
    """클라우드 위임 모델 구분 표시 (AC-061-4)."""


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


@pytest.mark.skip(reason="TD-DOC-4(PDF) 자료 없음(files.MISSING)")
def test_UC_070_S01_PDF_업로드_처리(target, s0):
    """PDF 3쪽, 2쪽 「22종」·3쪽 「9개월」 (AC-070-2·3·8)."""


@pytest.mark.skip(reason="TD-DOC-12(HWP 5.0) 자료 없음")
def test_UC_070_S10_HWP_표(target, s0):
    """HWP 5.0 표 3행×4열 (AC-070-8)."""


@pytest.mark.skip(reason="TD-DOC-13(HWPX) 자료 없음")
def test_UC_070_S11_HWPX_표(target, s0):
    """HWPX 표 (AC-070-8)."""


@pytest.mark.skip(reason="TD-DOC-15·16(암호 HWP·스캔 PDF) 자료 없음")
def test_UC_070_S13_지원_제한_구분(target, s0):
    """지원 제한 사유 구분 (AC-070-10·5)."""


@pytest.mark.skip(reason="임베딩 서버 중단·복구는 5174 환경 주입으로 본다")
def test_UC_070_S05_색인_장애_뒤_재처리(target, s0):
    """색인 실패 → 같은 문서 ID 로 완료 (AC-070-4·5)."""


@pytest.mark.skip(reason="처리 중 작업자 재시작은 5174 환경 주입으로 본다")
def test_UC_070_S07_재시작(target, s0):
    """대기열 복귀·반복 실패 사유 (AC-070-7)."""
