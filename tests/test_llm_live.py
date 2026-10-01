"""실제 LLM 검증 — Ollama 에 설정된 모델이 있을 때만 돈다.

    docker compose -f infra/docker-compose.yml --profile llm up -d ollama
    docker exec axlink-ollama ollama pull <llm_model>

폐쇄망 온프레미스 전제(QUR.RAG.001)라 외부 API 는 쓰지 않는다.
"""

import httpx
import pytest

from app.ai.llm import OllamaLlm
from app.config import settings
from tests.conftest import LIVE_ENABLED


def _model_ready() -> bool:
    try:
        res = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        names = [m.get("name", "") for m in res.json().get("models", [])]
    except Exception:
        return False
    return any(n.split(":")[0] == settings.llm_model.split(":")[0] for n in names)


# 실모델·실원천을 부른다. AXLINK_LIVE=1 일 때만 돈다(conftest). 꺼져 있으면 모델 확인 요청도
# 보내지 않는다 — 아래 skipif 가 LIVE_ENABLED 에서 먼저 끊긴다.
pytestmark = pytest.mark.live

live = pytest.mark.skipif(
    not LIVE_ENABLED or not _model_ready(), reason=f"Ollama 에 {settings.llm_model} 이 있어야 한다"
)


@live
def test_실모델이_문장을_돌려준다():
    port = OllamaLlm(settings.ollama_base_url, settings.llm_model, settings.llm_timeout)
    result = port.complete(
        "당신은 프로젝트 관리 보조자다. 한 문장으로만 답하라.",
        "AX Link 가 무엇의 줄임말인지 모른다면 모른다고 답하라.",
    )
    assert result.text.strip()
    assert result.model
