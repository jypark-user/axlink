"""AI 질의 API 통합. 대화·메시지·SSE 스트림을 실제 DB 로 돌린다.

모델은 대본대로 답하는 흉내(ScriptedLlm)를 쓴다. 여기서 보려는 건 문장 품질이 아니라
라우팅 결과가 어디로 흐르는지, 게이트가 모델 호출을 막는지, 출처와 인포그래픽이
저장되어 다시 열었을 때 그대로 나오는지다. 임베딩은 Fake 라 유사도가 뜻이 없어
게이트 문턱을 시험마다 직접 준다.
"""

import json
import uuid
from collections.abc import Iterator

import pytest

from app.ai.embedding import FakeEmbedding
from app.ai.port import LlmResult
from app.common import errors
from app.config import settings
from app.db import tx
from app.rag import indexing, number_guard
from app.rag import service as ask_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업


@pytest.fixture(autouse=True)
def _no_route_cache(request):
    """판정 캐시는 시험 사이에 남는다. 같은 DB 에서 먼저 돈 시나리오가 같은 질문의 판정을 남기면
    대본 모델의 판정을 건너뛰어 다른 경로로 답한다. 이 파일의 시험은 판정부터 본다"""
    if request.node.get_closest_marker("db") is None:
        return
    with tx() as cur:
        cur.execute("delete from route_cache")

_BODY = """# 과업지시서

## 1. 사업 개요
본 사업은 차세대 통합관제 시스템을 구축하는 사업이다. 사업 기간은 착수일로부터 10개월이다.

## 2. 납품 산출물
납품 산출물은 요구사항정의서, 설계서, 시험결과서를 포함한 22종이다. 각 산출물은 검수 후 납품한다.

## 3. 검수 기준
검수는 발주기관 담당자가 산출물별 체크리스트로 진행하며, 미비 항목은 보완 요청한다.
"""


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class ScriptedLlm:
    """라우팅 답(JSON)과 본문을 대본으로 받는다. 몇 번 불렸는지 센다."""

    def __init__(self, route: dict | None, text: str) -> None:
        self.route = route
        self.text = text
        self.stream_calls = 0
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, *, json_schema=None) -> LlmResult:
        text = json.dumps(self.route, ensure_ascii=False) if self.route else "모르겠다"
        return LlmResult(text=text, model="scripted")

    def stream(self, system: str, user: str, *, json_schema=None) -> Iterator[str]:
        """실모델처럼 {"answer": ...} JSON 을 조각내어 준다. 서비스가 그것을 풀어야 한다."""
        self.stream_calls += 1
        self.prompts.append(user)
        raw = json.dumps({"answer": self.text}, ensure_ascii=False) if json_schema else self.text
        for i in range(0, len(raw), 7):
            yield raw[i : i + 7]


def _events(res) -> list[tuple[str, dict]]:
    """SSE 원문을 (event, data) 목록으로. 프런트 lib/sse.ts 와 같은 규칙이다."""
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
            data.append(line[5:].lstrip())
    return out


@pytest.fixture
def indexed_document():
    sid = str(uuid.uuid4())
    with tx() as cur:
        # 다른 시험(수집·추적관계)이 같은 시드 사업에 청크를 남긴다. Fake 벡터는 텍스트별로
        # 결정적이라 청크 집합만 고정되면 근거 순서도 고정된다 — 그래서 사업을 먼저 비운다.
        cur.execute("delete from doc_chunk where project_id = %s", (PID,))
        indexing.reindex(
            cur,
            FakeEmbedding(1024),
            [
                indexing.IndexSource(
                    source_type="DOCUMENT_UPLOAD",
                    source_id=sid,
                    project_id=PID,
                    title="과업지시서",
                    body=_BODY,
                    uri="var/documents/sow.hwpx",
                )
            ],
        )
    yield sid
    with tx() as cur:
        cur.execute("delete from doc_chunk where source_id = %s", (sid,))


@pytest.fixture
def conversation(client, client_token):
    created: list[str] = []

    def _new(username: str = "r2", scope: list[str] | None = None) -> tuple[str, str]:
        token = client_token(username)
        res = client.post(
            "/api/conversations",
            json={"title": "시험 대화", "projectScope": scope if scope is not None else [PID]},
            headers=_auth(token),
        )
        assert res.status_code == 201, res.text
        created.append(res.json()["id"])
        return res.json()["id"], token

    yield _new
    with tx() as cur:
        cur.execute("delete from conversation where id = any(%s::uuid[])", (created,))


def _ask(client, token: str, conversation_id: str, question: str, scope=None):
    body = {"question": question, "projectScope": scope or []}
    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/messages",
        json=body,
        headers={**_auth(token), "Accept": "text/event-stream"},
    ) as res:
        assert res.status_code == 200, res.read()
        assert res.headers["content-type"].startswith("text/event-stream")
        return _events(res)


# ---------------------------------------------------------------- 대화


@requires_db
def test_대화는_내_것만_보이고_고정된_것이_위다(client, client_token, conversation):
    first, token = conversation()
    second, _ = conversation()
    res = client.patch(f"/api/conversations/{first}", json={"pinned": True}, headers=_auth(token))
    assert res.status_code == 200 and res.json()["pinned"] is True

    page = client.get("/api/conversations?size=50", headers=_auth(token)).json()
    ids = [c["id"] for c in page["content"]]
    assert ids.index(first) < ids.index(second)
    assert page["content"][ids.index(first)]["projectNames"] == ["차세대 통합관제 시스템 구축"]

    # 다른 사용자는 존재조차 모른다
    other = _auth(client_token("r3"))
    assert client.get(f"/api/conversations/{first}/messages", headers=other).status_code == 404
    res = client.patch(f"/api/conversations/{first}", json={"title": "x"}, headers=other)
    assert res.status_code == 404

    assert client.delete(f"/api/conversations/{first}", headers=_auth(token)).status_code == 204
    page = client.get("/api/conversations?size=50", headers=_auth(token)).json()
    assert first not in [c["id"] for c in page["content"]]


@requires_db
def test_접근할_수_없는_사업_범위는_거절한다(client, client_token):
    token = client_token("r3")
    res = client.post(
        "/api/conversations",
        json={"title": None, "projectScope": [str(uuid.uuid4())]},
        headers=_auth(token),
    )
    assert res.status_code == 403 and res.json()["code"] == "PROJECT_ACCESS_DENIED"


@requires_db
def test_추천_질문은_카탈로그_지표로_만든다(client, client_token):
    res = client.get(
        f"/api/conversations/suggestions?projectIds={PID}", headers=_auth(client_token("r2"))
    )
    assert res.status_code == 200
    questions = res.json()["questions"]
    assert len(questions) >= 3 and any("이행률" in q for q in questions)
    # 조사는 라벨 끝소리에 맞춘다. "수은(는)" 같은 병기는 없다
    assert not any("(는)" in q or "(가)" in q for q in questions)
    assert "열린 일반 이슈 수는 지금 몇 건인가요?" in questions
    assert "요구사항 이행률은 현재 몇 퍼센트인가요?" in questions


# ---------------------------------------------------------------- 질문 (문서 경로)


@requires_db
def test_문서_질문은_근거와_각주가_붙어_저장된다(
    client, conversation, indexed_document, monkeypatch
):
    scripted = ScriptedLlm(
        {"route": "DOCUMENT", "query": "납품 산출물"},
        "납품 산출물은 22종이다[1]. 검수 후 납품한다[1].",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", -1.0)  # Fake 임베딩이라 문턱을 내린다
    # Fake 벡터는 순서가 무작위다. DB 에 다른 청크가 남아 있어도 이 문서가 근거에 들게 넓힌다.
    monkeypatch.setattr(settings, "rag_top_k", 20)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "납품 산출물은 몇 종인가요?")

    names = [e for e, _ in events]
    assert names[0] == "start" and names[-1] == "done"
    assert names.index("sources") > names.index("delta")
    assert "infographic" not in names

    start = events[0][1]
    assert start["routing"]["type"] == "DOCUMENT"
    assert start["routing"]["rewrittenQuery"] == "납품 산출물"
    assert start["retrievedChunkCount"] >= 1

    text = "".join(d["text"] for e, d in events if e == "delta")
    assert text == "납품 산출물은 22종이다[1]. 검수 후 납품한다[1]."  # 22 는 근거 원문에 있다

    sources = next(d for e, d in events if e == "sources")["sources"]
    assert sources[0]["footnoteNo"] == 1
    assert sources[0]["sourceLabel"] == "과업지시서"
    assert sources[0]["sourceType"] == "DOCUMENT_UPLOAD"
    assert sources[0]["projectName"] == "차세대 통합관제 시스템 구축"
    assert sources[0]["externalUrl"] is None  # 저장 경로는 링크가 아니다
    # 출처에서 그 문서 화면으로 바로 간다 (SWFR.RAG.006)
    assert sources[0]["documentUrl"] == f"/p/{PID}/documents/{indexed_document}"
    # 위치는 조각의 표제 경로다. 근거 순서는 가짜 벡터라 고정이 아니어서 조각으로 찾는다
    cited = next(s for s in sources if "22종" in s["snippet"])
    assert cited["location"] == "과업지시서 > 2. 납품 산출물"

    done = events[-1][1]
    assert done["finishReason"] == "STOP"
    assert done["assistantMessageId"] == start["assistantMessageId"]
    assert scripted.stream_calls == 1
    assert "## 근거" in scripted.prompts[0] and "[1] 과업지시서" in scripted.prompts[0]

    # 다시 열면 같은 것이 나온다
    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    assert [m["role"] for m in messages] == ["USER", "ASSISTANT"]
    assistant = messages[1]
    assert assistant["content"] == text
    assert assistant["routing"]["type"] == "DOCUMENT"
    assert [s["footnoteNo"] for s in assistant["sources"]] == [
        s["footnoteNo"] for s in sources
    ]
    assert assistant["sources"][0]["snippet"] == sources[0]["snippet"]
    # 저장된 출처도 위치와 문서 링크를 그대로 돌려준다
    assert assistant["sources"][0]["location"] == sources[0]["location"]
    assert assistant["sources"][0]["documentUrl"] == sources[0]["documentUrl"]
    assert assistant["infographics"] == []

    page = client.get("/api/conversations?size=50", headers=_auth(token)).json()
    mine = next(c for c in page["content"] if c["id"] == conversation_id)
    assert mine["messageCount"] == 2 and mine["lastMessageAt"] is not None


@requires_db
def test_근거가_부족하면_모델을_부르지_않는다(client, conversation, indexed_document, monkeypatch):
    scripted = ScriptedLlm({"route": "DOCUMENT"}, "이 문장은 나오면 안 된다")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "우주 정거장의 도킹 절차는?")

    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "맞는 내용을 찾지 못해" in text and "0.99" in text
    assert next(d for e, d in events if e == "sources")["sources"] == []
    # 문서가 있는데 맞는 것이 없다. 문서가 아예 없는 경우와 다른 종류로 끝난다
    assert events[-1][1]["finishReason"] == "NO_RELEVANT_DOCUMENTS"
    # 질문과 무관한 고정 현황 그림을 대신 붙이지 않는다
    assert not [d for e, d in events if e == "infographic"]
    assert events[0][1]["retrievedChunkCount"] == 0
    assert scripted.stream_calls == 0

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    assert messages[1]["content"] == text and messages[1]["sources"] == []


@requires_db
def test_색인이_비어_있으면_그렇다고_답한다(client, conversation, monkeypatch):
    scripted = ScriptedLlm({"route": "DOCUMENT"}, "x")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    with tx() as cur:
        empty = cur.execute(
            "select count(*) as n from doc_chunk where project_id = %s", (PID,)
        ).fetchone()["n"] == 0
    if not empty:
        pytest.skip("시드 사업에 색인이 남아 있다")

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "아무 질문")
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "올라온 문서·이슈가 아직 없어" in text and scripted.stream_calls == 0
    assert events[-1][1]["finishReason"] == "NO_DOCUMENTS"


class DownLlm(ScriptedLlm):
    """모델 서버가 내려간 상태. 실제 어댑터처럼 AI_UNAVAILABLE 을 낸다."""

    def complete(self, system: str, user: str, *, json_schema=None) -> LlmResult:
        raise errors.ApiError(503, "AI_UNAVAILABLE", "LLM 에 닿지 못했습니다: [Errno 111] refused")

    def stream(self, system: str, user: str, *, json_schema=None) -> Iterator[str]:
        self.stream_calls += 1
        raise errors.ApiError(503, "AI_UNAVAILABLE", "LLM 에 닿지 못했습니다: [Errno 111] refused")


@requires_db
def test_모델_서버가_없으면_쓸_수_없다고_안내하고_원문은_감춘다(client, conversation, monkeypatch):
    scripted = DownLlm(None, "")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "일반 이슈가 몇 건이야")
    name, data = events[-1]
    assert name == "error" and data["code"] == "AI_UNAVAILABLE", events
    assert "쓸 수 없" in data["message"] and "Errno" not in data["message"]
    assert scripted.stream_calls == 0


@requires_db
def test_판정_캐시가_있는_집계_질문은_모델_장애_때_집계_값으로_답한다(
    client, conversation, monkeypatch
):
    """DEF-V041. 판정이 캐시에 있으면 판정 단계에서 모델을 부르지 않아 장애를 모른 채 생성을
    시도한다. 생성이 실패하면 집계 값으로 서버 문안을 낸다. 모델 문장은 하나도 나가지 않는다."""
    question = "이슈가 모두 몇 건인지 알려줘"
    with tx() as cur:
        cur.execute("delete from route_cache where question = %s", (question,))
        expected = cur.execute(
            "select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL'",
            (PID,),
        ).fetchone()["n"]
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)  # 문서 근거는 없는 셈 친다
    # 1) 모델이 살아 있을 때 한 번 답해 판정을 캐시에 남긴다
    alive = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "issue_count", "dimensions": [],
         "template": "STAT_CARD", "title": "이슈 건수", "query": "이슈 건수"},
        f"현재 이슈는 모두 {expected}건입니다.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: alive)
    conversation_id, token = conversation()
    first = _ask(client, token, conversation_id, question)
    assert first[-1][1]["finishReason"] == "STOP", first

    # 2) 모델 서버가 내려간 뒤 같은 질문
    down = DownLlm(None, "")
    monkeypatch.setattr(ask_service, "llm_port", lambda: down)
    events = _ask(client, token, conversation_id, question)
    assert events[0][1]["routing"]["routeCached"] is True
    assert down.stream_calls == 1  # 생성은 한 번 시도한다(AC-060-9 v0.2.5)
    names = [e for e, _ in events]
    assert "error" not in names, events
    assert names[-1] == "done" and events[-1][1]["finishReason"] == "MODEL_DOWN"
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "쓸 수 없" in text and f"이슈 건수(결함 제외): {expected}" in text, text
    assert "Errno" not in text


# ---------------------------------------------------------------- 질문 (집계 경로)


@requires_db
def test_값이_하나인_집계는_그림_없이_글로만_답한다(client, conversation, monkeypatch):
    """문장이 숫자를 말하는데 카드까지 붙이면 답이 무거워진다(ARC-013 4절). 값은 그래도
    프롬프트와 수치 검문에 들어간다."""
    with tx() as cur:
        expected = cur.execute(
            "select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL'",
            (PID,),
        ).fetchone()["n"]
    scripted = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "issue_count", "dimensions": [],
         "template": "STAT_CARD", "title": "이슈 건수", "query": "이슈 건수"},
        f"현재 이슈는 모두 {expected}건입니다.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)  # 문서 근거는 없는 셈 친다

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈가 몇 건이죠?")
    names = [e for e, _ in events]
    assert "infographic" not in names
    assert names[-1] == "done" and events[-1][1]["finishReason"] == "STOP"

    start = events[0][1]["routing"]
    assert start["type"] == "AGGREGATE" and start["measureKey"] == "issue_count"
    assert start["viz"] is None

    # 프롬프트에 집계 값이 들어갔고, 그 값만 인용한 답은 검문을 통과한다
    assert f"이슈 건수(결함 제외): {expected}" in scripted.prompts[0]
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "※" not in text and "[그림" not in text

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    assert messages[1]["infographics"] == []
    assert messages[1]["routing"]["viz"] is None


@requires_db
def test_질문에_적은_기간으로_집계한다(client, conversation, monkeypatch):
    """GH-123. "이번 달" 을 물었는데 기간 필터가 없어 그림이 수집 첫날부터 그려졌다."""
    seen: list = []
    real_run = ask_service.semantic.run

    def spy(cur, principal, spec, *args, **kwargs):
        seen.append(spec.query.filters)
        return real_run(cur, principal, spec, *args, **kwargs)

    scripted = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "progress_representative_pct",
         "dimensions": ["period_day"], "template": "LINE_CHART", "title": "진척 추세",
         "query": "진척 추세"},
        "이번 달 진척 추세입니다.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(ask_service.semantic, "run", spy)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이번 달 진척 추세 보여줘")
    assert events[-1][0] == "done"
    assert seen, "집계를 부르지 않았다"
    period = [(f.field, f.op, f.value) for f in seen[0]]
    assert period == [("period", "IN_MONTH", "current")]


@requires_db
def test_집계에_없는_숫자는_화면에_나가기_전에_막는다(client, conversation, monkeypatch):
    """QUR.RAG.002, ARC-017. 지어낸 숫자는 어떤 조각에도 실리지 않고 저장도 안 된다."""
    with tx() as cur:
        expected = cur.execute(
            "select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL'",
            (PID,),
        ).fetchone()["n"]
    scripted = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"},
        f"현재 이슈는 모두 {expected}건입니다. 그중 977건이 지연입니다. 확인해 보십시오.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈 건수는?")
    deltas = [d["text"] for e, d in events if e == "delta"]
    text = "".join(deltas)
    assert all("977" not in piece for piece in deltas)  # 검사 전에도 나간 적이 없다
    assert f"현재 이슈는 모두 {expected}건입니다." in text  # 맞는 문장은 그대로 나간다
    assert number_guard.BLOCKED_NOTE in text and "확인해 보십시오." in text
    assert events[-1][1]["finishReason"] == "NUMBER_GUARD"

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    assert "977" not in messages[1]["content"]  # 저장 본문도 화면과 같다
    assert number_guard.BLOCKED_NOTE in messages[1]["content"]


@requires_db
def test_질문에_나온_숫자를_그대로_말해도_근거가_아니다(client, conversation, monkeypatch):
    scripted = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"},
        "네, 이슈는 500건이 넘습니다.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈가 500건 넘었어?")
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "500" not in text
    assert events[-1][1]["finishReason"] == "NUMBER_GUARD"


@requires_db
def test_카탈로그_검증에_막힌_집계는_문서_경로로_내려간다(
    client, conversation, indexed_document, monkeypatch
):
    # 허용되지 않는 차원은 from_choice 가 버리므로, 조립 단계에서 막히는 건
    # 접근 범위 밖 사업뿐이다. 범위는 prepare 가 먼저 거르니 여기서는 지표를 잘못 골라 본다.
    scripted = ScriptedLlm({"route": "AGGREGATE", "measure": "없는_지표"}, "문서로 답한다[1]")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", -1.0)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "산출물 검수 기준은?")
    assert events[0][1]["routing"]["type"] == "DOCUMENT"
    assert events[0][1]["routing"]["measureKey"] is None
    assert "infographic" not in [e for e, _ in events]


# ---------------------------------------------------------------- 범위 · 피드백


@requires_db
def test_질문의_사업_범위는_접근_범위_안이어야_한다(client, conversation):
    conversation_id, token = conversation()
    res = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"question": "x", "projectScope": [str(uuid.uuid4())]},
        headers=_auth(token),
    )
    assert res.status_code == 403


@requires_db
def test_피드백은_내_대화의_답변에만_남는다(client, client_token, conversation, monkeypatch):
    scripted = ScriptedLlm({"route": "DOCUMENT"}, "x")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "질문")
    assistant_id = events[0][1]["assistantMessageId"]
    user_id = events[0][1]["userMessageId"]

    res = client.post(
        f"/api/messages/{assistant_id}/feedback", json={"feedback": "UP"}, headers=_auth(token)
    )
    assert res.status_code == 204
    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    assert messages[1]["feedback"] == "UP" and messages[0]["feedback"] is None

    # 사용자 메시지에는 못 남기고, 남의 답변에도 못 남긴다
    up = {"feedback": "UP"}
    res = client.post(f"/api/messages/{user_id}/feedback", json=up, headers=_auth(token))
    assert res.status_code == 404
    other = _auth(client_token("r3"))
    res = client.post(f"/api/messages/{assistant_id}/feedback", json=up, headers=other)
    assert res.status_code == 404


# ---------------------------------------------------------------- 목록 질문


@pytest.fixture
def indexed_entities():
    """이슈 둘·요구사항 하나. 목록 질문은 종류로 고르므로 다른 종류가 섞여 있어야 시험이 된다."""
    sids = [str(uuid.uuid4()) for _ in range(3)]
    specs = [
        ("ISSUE", "커넥터 시험 — Redmine 증분 수집", "updated_on 필터로 100건씩 받는다."),
        ("ISSUE", "근거 게이트 임계값 결정", "실측 분포를 보고 0.55 로 둔다."),
        ("REQUIREMENT", "커넥터는 공통 인터페이스를 구현한다", "신규 도구는 구현체 추가만으로."),
    ]
    with tx() as cur:
        cur.execute("delete from doc_chunk where project_id = %s", (PID,))
        indexing.reindex(
            cur,
            FakeEmbedding(1024),
            [
                indexing.IndexSource(
                    source_type=kind, source_id=sid, project_id=PID, title=title, body=body,
                    uri=None,
                )
                for sid, (kind, title, body) in zip(sids, specs, strict=True)
            ],
        )
    yield sids
    with tx() as cur:
        cur.execute("delete from doc_chunk where source_id = any(%s::uuid[])", (sids,))


@requires_db
def test_목록_질문은_종류_전체를_근거로_답한다(client, conversation, indexed_entities, monkeypatch):
    """표를 못 만들 때의 길이다. 종류로 모은 청크가 근거가 되고 게이트는 종류로 통과한다.

    표준 모델에 행이 있으면 표가 답하므로(ARC-013) 이 길로 오지 않는다. 표가 없는 종류만
    여기로 온다. 표를 못 만드는 상황을 만들어 그 길을 시험한다.
    """
    scripted = ScriptedLlm(
        {"route": "DOCUMENT", "list": "ISSUE", "query": "이슈 목록"},
        "이슈는 총 2건이다. 커넥터 시험[1]과 근거 게이트 임계값 결정[2]이다.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(ask_service.entity_table, "build", lambda *a, **k: None)
    # 문턱은 기본값 그대로 둔다. 목록은 유사도가 아니라 종류로 통과해야 한다.

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈 목록 조회")
    names = [e for e, _ in events]
    assert names[0] == "start" and names[-1] == "done"

    start = events[0][1]
    assert start["routing"]["type"] == "DOCUMENT"
    assert start["routing"]["listing"] == "ISSUE"
    assert start["retrievedChunkCount"] == 2  # 요구사항은 섞이지 않는다

    sources = next(d for e, d in events if e == "sources")["sources"]
    assert [s["sourceType"] for s in sources] == ["ISSUE", "ISSUE"]
    assert [s["footnoteNo"] for s in sources] == [1, 2]
    # 제목 순 — 근거 번호가 실행마다 바뀌지 않는다
    labels = [s["sourceLabel"] for s in sources]
    assert labels == ["근거 게이트 임계값 결정", "커넥터 시험 — Redmine 증분 수집"]

    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "※" not in text  # 총 2건은 목록 범위 줄에 있으므로 지어낸 숫자가 아니다
    assert "## 목록 범위" in scripted.prompts[0] and "전체 2건" in scripted.prompts[0]
    assert events[-1][1]["finishReason"] == "STOP"


@pytest.fixture
def seeded_risk() -> Iterator[str]:
    """리스크 한 건. 이 시험이 기대는 행은 시험이 직접 만든다.

    전에는 다른 시험(수집·승격)이 남긴 리스크에 기대어, 빈 시험 DB 에서 처음 돌면 표 대신
    현황 그림으로 내려가 실패했다.
    """
    with tx() as cur:
        cur.execute(
            """
            insert into risk (project_id, title, severity, status)
            values (%s, %s, 'HIGH', 'OPEN')
            returning id
            """,
            (PID, "Redmine 실서버 수집 시험 지연"),
        )
        rid = str(cur.fetchone()["id"])
    yield rid
    with tx() as cur:
        cur.execute("delete from risk where id = %s", (rid,))


@requires_db
def test_색인에_없어도_표준_모델에_있으면_답한다(
    client, conversation, indexed_entities, seeded_risk, monkeypatch
):
    """리스크는 색인 청크가 없다. 그래도 표준 모델에 행이 있으면 표로 답한다 (ARC-013).

    청크 유사도만으로 막으면 될 답을 막는다. 표의 행은 SQL 이 꺼낸 것이라 근거가 있다.
    """
    route = {"route": "DOCUMENT", "list": "RISK", "listFilter": "ALL", "query": "리스크 목록"}
    scripted = ScriptedLlm(route, "등록된 리스크입니다. " + chr(10) + "[그림 1]")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "리스크 목록")
    assert events[-1][1]["finishReason"] == "STOP"
    assert scripted.stream_calls == 1
    block = next(d for e, d in events if e == "infographic")
    assert block["template"] == "DATA_TABLE" and block["data"]["rows"]
    assert "Redmine 실서버 수집 시험 지연" in json.dumps(block["data"]["rows"], ensure_ascii=False)


@requires_db
def test_청크도_표도_없으면_모델을_부르지_않는다(
    client, conversation, indexed_entities, monkeypatch
):
    """근거 게이트(SWFR.RAG.007)는 그대로다. 낼 것이 없으면 답을 만들지 않는다."""
    route = {"route": "DOCUMENT", "list": "RISK", "query": "리스크 목록"}
    scripted = ScriptedLlm(route, "안 불려야 한다")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(ask_service.entity_table, "build", lambda *a, **k: None)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "리스크 목록")
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "리스크" in text and "없어" in text
    assert events[-1][1]["finishReason"] == "NO_DATA"
    assert scripted.stream_calls == 0


# ---------------------------------------------------------------- 결합 응답 (SWFR.RAG.005)


@requires_db
def test_집계와_문서_근거가_둘_다_있으면_한_답에_결합한다(
    client, conversation, indexed_document, monkeypatch
):
    """지표로 셀 수 있는 질문에 문서 근거도 걸리면 MIXED 다. 집계 값과 문서 조각이 같은
    프롬프트에 들어가고, 답에는 집계 수치와 문서 출처가 함께 나온다. 수치는 두 재료 안의
    것만 통과한다."""
    with tx() as cur:
        expected = cur.execute(
            "select count(*) as n from issue where project_id = %s and issue_kind = 'GENERAL'",
            (PID,),
        ).fetchone()["n"]
    scripted = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "issue_count", "dimensions": [],
         "template": "STAT_CARD", "title": "이슈 건수", "query": "납품 산출물 이슈 건수"},
        f"이슈는 {expected}건이고, 납품 산출물은 22종이다[1].",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", -1.0)  # Fake 임베딩이라 문턱을 내린다
    monkeypatch.setattr(settings, "rag_top_k", 20)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "납품 산출물은 몇 종이고 이슈는 몇 건이야?")
    names = [e for e, _ in events]
    start = events[0][1]
    assert start["routing"]["type"] == "MIXED"
    assert start["routing"]["measureKey"] == "issue_count"
    assert start["retrievedChunkCount"] >= 1

    # 두 재료가 한 프롬프트에 있다
    prompt = scripted.prompts[0]
    assert "## 집계 값" in prompt and f"이슈 건수(결함 제외): {expected}" in prompt
    assert "## 근거" in prompt and "[1] 과업지시서" in prompt

    # 답에는 집계 수치가 그대로, 문서 출처가 각주로 붙는다. 둘 다 지어낸 숫자가 아니다
    assert names[-1] == "done" and events[-1][1]["finishReason"] == "STOP"
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert text == f"이슈는 {expected}건이고, 납품 산출물은 22종이다[1]."
    sources = next(d for e, d in events if e == "sources")["sources"]
    assert sources and sources[0]["sourceType"] == "DOCUMENT_UPLOAD"
    assert sources[0]["sourceLabel"] == "과업지시서"

    # 저장된 답도 같은 길(MIXED)과 출처를 돌려준다
    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    assert messages[1]["routing"]["type"] == "MIXED"
    assert messages[1]["sources"][0]["sourceType"] == "DOCUMENT_UPLOAD"
