"""실제 bge-m3 검증 — Ollama 가 떠 있을 때만 돈다.

    docker compose -f infra/docker-compose.yml --profile llm up -d ollama
    docker exec axlink-ollama ollama pull bge-m3

폐쇄망 온프레미스 전제(QUR.RAG.001)라 외부 API 는 쓰지 않는다.
"""

import httpx
import pytest

from app.ai.embedding import OllamaEmbedding
from app.config import settings
from tests.conftest import LIVE_ENABLED


def _model_ready() -> bool:
    try:
        res = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        names = [m.get("name", "") for m in res.json().get("models", [])]
    except Exception:
        return False
    return any(n.split(":")[0] == settings.embedding_model for n in names)


# 실모델·실원천을 부른다. AXLINK_LIVE=1 일 때만 돈다(conftest). 꺼져 있으면 모델 확인 요청도
# 보내지 않는다 — 아래 skipif 가 LIVE_ENABLED 에서 먼저 끊긴다.
pytestmark = pytest.mark.live

live = pytest.mark.skipif(
    not LIVE_ENABLED or not _model_ready(), reason="Ollama 에 bge-m3 가 있어야 한다"
)


@pytest.fixture(scope="module")
def port() -> OllamaEmbedding:
    return OllamaEmbedding(
        settings.ollama_base_url, settings.embedding_model, 1024, settings.embedding_batch, 60.0
    )


@live
def test_real_model_returns_declared_dimension(port):
    vectors = port.embed(["요구사항 이행률은 어떻게 계산하나"])
    assert len(vectors) == 1
    assert len(vectors[0]) == port.dimension() == 1024


@live
def test_batch_keeps_input_order(port):
    texts = ["진척률", "리스크", "산출물"]
    vectors = port.embed(texts)
    assert len(vectors) == 3
    assert vectors[0] == port.embed(["진척률"])[0]


@live
def test_korean_similarity_is_meaningful(port):
    """한국어를 실제로 이해하는지 — 가까운 문장이 먼 문장보다 유사해야 한다(SWFR.RAG.004)."""
    query, near, far = port.embed(
        [
            "요구사항 이행률이 얼마나 되나요",
            "전체 요구사항 중 검증까지 끝난 비율을 산출한다",
            "점심으로 김치찌개를 먹었다",
        ]
    )

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cosine(query, near) > cosine(query, far)
