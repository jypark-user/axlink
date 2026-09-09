"""LlmPort (SWFR.RAG.002) — 계약과 어댑터.

모델·실행환경을 바꿔도 상위가 변하지 않으려면 계약이 좁고 안정적이어야 한다.
실모델 검증은 test_llm_live.py 가 Ollama 가 떠 있을 때만 한다.
"""

import httpx
import pytest

from app.ai import llm
from app.common import errors


def _client_with(handler, monkeypatch):
    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: real(transport=transport))


def test_페이크는_결정적이다():
    port = llm.FakeLlm()
    first = port.complete("지시", "질문")
    second = port.complete("지시", "질문")
    assert first == second
    assert first.model == "fake"
    # 입력이 다르면 답도 다르다 — 프롬프트 조립 실수를 시험이 잡을 수 있게
    assert port.complete("지시", "다른 질문").text != first.text


def test_올라마_어댑터는_chat_계약을_지킨다(monkeypatch):
    seen = {}

    def handler(request):
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "qwen3:4b",
            "message": {"role": "assistant", "content": "  응답 문장  "},
        })

    _client_with(handler, monkeypatch)
    result = llm.OllamaLlm("http://localhost:11434", "qwen3:4b", 5).complete("지시", "질문")

    assert result.text == "응답 문장"          # 공백은 계약 밖이다
    assert result.model == "qwen3:4b"
    assert seen["stream"] is False              # 동기 계약 — 스트리밍은 M4 에서 판단
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]


def test_빈_응답은_실패로_드러난다(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"model": "m", "message": {"content": ""}})

    _client_with(handler, monkeypatch)
    with pytest.raises(errors.ApiError) as exc:
        llm.OllamaLlm("http://x", "m", 5).complete("s", "u")
    assert exc.value.code == "AI_UNAVAILABLE"


def test_불통은_AI_UNAVAILABLE_로_올라간다(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _client_with(handler, monkeypatch)
    with pytest.raises(errors.ApiError) as exc:
        llm.OllamaLlm("http://x", "m", 5).complete("s", "u")
    assert exc.value.status == 503 and exc.value.code == "AI_UNAVAILABLE"


def test_선택_지점은_설정을_따른다(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "fake")
    assert isinstance(llm.llm_port(), llm.FakeLlm)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    assert isinstance(llm.llm_port(), llm.OllamaLlm)
