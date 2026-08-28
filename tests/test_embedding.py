"""임베딩 포트 계약. Fake 어댑터는 결정성이 계약이다."""

import httpx
import pytest

from app.ai.embedding import FakeEmbedding, OllamaEmbedding
from app.common.errors import ApiError
from app.rag import vector


def test_fake_is_deterministic_and_normalized():
    port = FakeEmbedding(1024)
    first = port.embed(["요구사항 이행률은 얼마인가"])[0]
    second = port.embed(["요구사항 이행률은 얼마인가"])[0]

    assert first == second
    assert len(first) == port.dimension() == 1024
    assert abs(sum(v * v for v in first) ** 0.5 - 1.0) < 1e-9


def test_fake_separates_different_texts():
    port = FakeEmbedding(1024)
    a, b = port.embed(["진척률", "리스크"])
    assert a != b


def test_empty_input_makes_no_call():
    assert FakeEmbedding(1024).embed([]) == []


def test_vector_literal_roundtrip():
    values = [0.125, -0.5, 0.0]
    assert vector.from_literal(vector.to_literal(values)) == values


def test_unreachable_model_maps_to_ai_unavailable():
    port = OllamaEmbedding("http://127.0.0.1:1", "bge-m3", 1024, 32, 0.5)
    with pytest.raises(ApiError) as exc:
        port.embed(["아무 문장"])
    assert exc.value.code == "AI_UNAVAILABLE"


def test_wrong_dimension_is_rejected(monkeypatch):
    """모델이 다른 차원을 주면 색인하지 않고 실패시킨다 — 조용히 망가지는 게 최악이다."""
    port = OllamaEmbedding("http://model.invalid", "wrong", 1024, 32, 1.0)

    def fake_post(self, url, json=None, **kwargs):  # noqa: ARG001
        return httpx.Response(200, json={"embeddings": [[0.0] * 768]})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    with pytest.raises(ApiError) as exc:
        port.embed(["문장"])
    assert exc.value.code == "AI_UNAVAILABLE"
    assert "차원" in exc.value.message
