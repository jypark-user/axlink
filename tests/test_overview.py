"""사업 현황 경로 (ARC-015 · SWFR.RAG.005 · SWFR.RAG.007).

문서를 가리키지 않는 일반 질문은 현황 그림으로 답한다. 근거 게이트에 막힌 질문도 그리로
내려간다. 값은 전부 시맨틱 레이어에서 온다. 데이터가 없으면 예전처럼 막는다.
"""

import json
from collections.abc import Iterator

import pytest

from app.ai.port import LlmResult
from app.auth.models import AuthPrincipal
from app.config import settings
from app.db import tx
from app.rag import overview, routing
from app.rag import service as ask_service
from tests.conftest import requires_db
from tests.test_widget_generation import _catalog

PID = "c0000000-0000-4000-8000-000000000001"


def test_현황_판정은_지표_없이도_선다():
    d = routing.from_choice(_catalog(), {"route": "OVERVIEW", "query": "사업 현황"})
    assert d.type == routing.OVERVIEW and d.rewritten == "사업 현황"
    # 지표가 같이 오면 집계가 우선이다. 현황은 지표를 못 고른 일반 질문의 자리다
    both = routing.from_choice(
        _catalog(), {"route": "OVERVIEW", "measure": "open_issue_count", "template": "STAT_CARD"}
    )
    assert both.type == routing.AGGREGATE


def test_라우팅_프롬프트가_현황_경로를_안내한다():
    prompt = routing.system_prompt(_catalog())
    assert '"route": "OVERVIEW"' in prompt and "잘 되고 있어?" in prompt
    assert '"route": "OFF_TOPIC"' in prompt


def test_무관_판정은_따로_선다():
    d = routing.from_choice(_catalog(), {"route": "OFF_TOPIC"})
    assert d.type == routing.OFF_TOPIC
    # 지표나 목록이 같이 오면 무관이 아니다. 모델이 헷갈린 것이다
    with_list = routing.from_choice(_catalog(), {"route": "OFF_TOPIC", "list": "ISSUE"})
    assert with_list.type == routing.DOCUMENT and with_list.listing == "ISSUE"


@requires_db
def test_현황_그림은_카탈로그에서_나오고_비면_비운다():
    principal = AuthPrincipal(
        user_id="d0000000-0000-4000-8000-000000000002",
        org_id="00000000-0000-0000-0000-000000000000",
        org_type="CLIENT",
        role="SUPER_ADMIN",
    )
    with tx() as cur:
        made = overview.build(cur, principal, [PID], first_slot=3)
    assert made, "시드 사업에는 이슈·산출물·리스크가 있어 그림이 나와야 한다"
    assert [b.slot for b in made] == list(range(3, 3 + len(made)))
    assert len(made) <= overview.MAX_BLOCKS
    assert all(b.lines for b in made)
    # 값이 없는 지표는 그림이 되지 않는다
    assert all("값 없음" not in line for b in made for line in b.lines)


class _Scripted:
    def __init__(self, route: dict, text: str) -> None:
        self.route, self.text = route, text
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, *, json_schema=None) -> LlmResult:
        return LlmResult(text=json.dumps(self.route, ensure_ascii=False), model="scripted")

    def stream(self, system: str, user: str, *, json_schema=None) -> Iterator[str]:
        self.prompts.append(user)
        raw = json.dumps({"answer": self.text}, ensure_ascii=False) if json_schema else self.text
        yield raw


def _ask(client, token: str, cid: str, question: str) -> list[tuple[str, dict]]:
    out, ev = [], None
    with client.stream(
        "POST",
        f"/api/conversations/{cid}/messages",
        json={"question": question, "projectScope": []},
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
    ) as res:
        assert res.status_code == 200, res.read()
        for line in res.iter_lines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:") and ev:
                out.append((ev, json.loads(line[5:])))
    return out


@pytest.fixture
def conversation(client, client_token):
    token = client_token("r2")
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/api/conversations", json={"title": "현황", "projectScope": [PID]}, headers=headers
    )
    assert res.status_code == 201, res.text
    yield res.json()["id"], token
    client.delete(f"/api/conversations/{res.json()['id']}", headers=headers)


@requires_db
def test_현황_질문은_현황_그림으로_답한다(client, conversation, monkeypatch):
    scripted = _Scripted(
        {"route": "OVERVIEW", "query": "사업 현황"}, "대체로 순조롭습니다. [그림 1]"
    )
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)  # 문서 근거는 없는 셈

    cid, token = conversation
    events = _ask(client, token, cid, "지금 사업 잘 되고 있어?")
    start = events[0][1]["routing"]
    assert start["type"] == "OVERVIEW"
    made = [d for e, d in events if e == "infographic"]
    assert made and [b["slot"] for b in made] == list(range(1, len(made) + 1))
    assert events[-1][1]["finishReason"] == "STOP"
    # 프롬프트에 그림 절이 들어갔고, 서버가 쓴 안내문은 없다(현황 경로는 못 찾은 게 아니다)
    assert "## 그림 1" in scripted.prompts[0]
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert not text.startswith(overview.REFERENCE_LEAD.strip()[:10])


@requires_db
def test_근거에_막힌_문서_질문은_답하지_않고_참고_현황만_붙인다(client, conversation, monkeypatch):
    """SWFR.RAG.007, ARC-017. 모델은 원질문에 답하지 않는다. 현황은 참고로만 보인다."""
    scripted = _Scripted({"route": "DOCUMENT", "query": "걱정"}, "안 불려야 한다")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)

    cid, token = conversation
    events = _ask(client, token, cid, "뭐가 제일 걱정이야?")
    assert events[0][1]["routing"]["type"] == "OVERVIEW"
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert text.startswith("질문에 맞는 문서 근거를 찾지 못해 답변을 만들지 않았습니다")
    assert "참고 현황" in text and "답의 근거가 아닙니다" in text
    assert "안 불려야" not in text
    assert scripted.prompts == []  # 본문을 쓰는 모델 호출이 없다
    made = [d for e, d in events if e == "infographic"]
    assert made and all(b["title"].startswith(overview.REFERENCE_TITLE) for b in made)
    # 그림 표식은 서버가 붙인다. 문서 출처는 없다
    assert all(f"[그림 {b['slot']}]" in text for b in made)
    assert next(d for e, d in events if e == "sources")["sources"] == []
    assert events[-1][1]["finishReason"] == "NO_EVIDENCE"
    # 내려간 판정은 캐시하지 않는다. 다음엔 다시 묻는다
    with tx() as cur:
        n = cur.execute(
            "select count(*) as n from route_cache where question like %s", ("%걱정%",)
        ).fetchone()["n"]
    assert n == 0


@requires_db
def test_무관한_질문은_현황으로_내려가지_않는다(client, conversation, monkeypatch):
    """날씨를 물었는데 진척률이 나오면 안 된다. 모델도 부르지 않는다."""
    scripted = _Scripted({"route": "OFF_TOPIC"}, "안 불려야 한다")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)

    cid, token = conversation
    events = _ask(client, token, cid, "오늘 날씨 어때?")
    text = "".join(d["text"] for e, d in events if e == "delta")
    assert "사업" in text and "만 답합니다" in text
    assert not [d for e, d in events if e == "infographic"]
    assert events[-1][1]["finishReason"] == "NO_EVIDENCE"
    assert scripted.prompts == []


@requires_db
def test_무관_판정이어도_근거가_있으면_문서로_답한다(client, conversation, monkeypatch):
    """모델이 "인수 조건이 뭐야" 를 무관으로 봤다. 근거가 있으면 근거가 판정을 이긴다."""
    scripted = _Scripted({"route": "OFF_TOPIC"}, "근거대로 답합니다[1].")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.0)  # 청크만 있으면 통과

    with tx() as cur:
        has_chunks = cur.execute(
            "select count(*) as n from doc_chunk where project_id = %s", (PID,)
        ).fetchone()["n"] > 0
    if not has_chunks:
        pytest.skip("시드 사업에 색인이 없다")
    cid, token = conversation
    events = _ask(client, token, cid, "인수 조건이 뭐야?")
    assert events[0][1]["routing"]["type"] == "DOCUMENT"
    assert events[-1][1]["finishReason"] == "STOP"
    assert scripted.prompts  # 모델이 본문을 썼다


@requires_db
def test_현황_그림도_없으면_예전처럼_막는다(client, conversation, monkeypatch):
    scripted = _Scripted({"route": "DOCUMENT", "query": "x"}, "안 불려야 한다")
    monkeypatch.setattr(ask_service, "llm_port", lambda: scripted)
    monkeypatch.setattr(settings, "rag_min_similarity", 0.99)
    monkeypatch.setattr(ask_service.overview, "build", lambda *a, **k: [])

    cid, token = conversation
    events = _ask(client, token, cid, "아무거나")
    assert events[-1][1]["finishReason"] == "NO_EVIDENCE"
    assert scripted.prompts == []
