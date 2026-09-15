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
from app.config import settings
from app.db import tx
from app.rag import indexing
from app.rag import service as ask_service
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"  # 시드 사업

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
    assert sources[0]["documentUrl"] == f"/p/{PID}/documents"

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
    assert assistant["infographic"] is None

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
    assert "근거" in text and "0.99" in text
    assert next(d for e, d in events if e == "sources")["sources"] == []
    assert events[-1][1]["finishReason"] == "NO_EVIDENCE"
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
    assert "색인된 문서" in text and scripted.stream_calls == 0


# ---------------------------------------------------------------- 질문 (집계 경로)


@requires_db
def test_집계_질문은_인포그래픽을_싣고_값은_DB_에서_온다(client, conversation, monkeypatch):
    with tx() as cur:
        expected = cur.execute(
            "select count(*) as n from issue where project_id = %s", (PID,)
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
    assert names.index("infographic") > names.index("sources")
    assert names[-1] == "done" and events[-1][1]["finishReason"] == "STOP"

    start = events[0][1]["routing"]
    assert start["type"] == "AGGREGATE" and start["measureKey"] == "issue_count"
    assert start["viz"] == "STAT_CARD"

    infographic = next(d for e, d in events if e == "infographic")
    assert infographic["template"] == "STAT_CARD" and infographic["title"] == "이슈 건수"
    assert infographic["data"]["measure"] == "issue_count"
    assert infographic["data"]["rows"][0]["values"]["value"] == expected
    assert infographic["data"]["appliedProjectIds"] == [PID]

    # 프롬프트에 집계 값이 들어갔고, 그 값만 인용한 답은 검문을 통과한다
    assert f"이슈 건수: {expected}" in scripted.prompts[0]
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "※" not in text

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    saved = messages[1]["infographic"]
    assert saved["template"] == "STAT_CARD"
    assert saved["data"]["rows"] == infographic["data"]["rows"]
    assert messages[1]["routing"]["viz"] == "STAT_CARD"


@requires_db
def test_집계에_없는_숫자를_지어내면_표시가_붙는다(client, conversation, monkeypatch):
    scripted = ScriptedLlm(
        {"route": "AGGREGATE", "measure": "issue_count", "template": "STAT_CARD"},
        "이슈는 모두 977건이고 그중 41건이 지연입니다.",
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    conversation_id, token = conversation()
    events = _ask(client, token, conversation_id, "이슈 건수는?")
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "977" in text and "※" in text and "41" in text.split("※")[1]
    assert events[-1][1]["finishReason"] == "NUMBER_GUARD"

    messages = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=_auth(token)
    ).json()
    assert "※" in messages[1]["content"]  # 표시까지 저장된다


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
