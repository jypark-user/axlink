"""정형화 초안의 LLM 개입을 실모델로 검증한다. Ollama 에 설정된 모델이 있을 때만 돈다.

    docker compose -f infra/docker-compose.yml --profile llm up -d ollama
    docker exec axlink-ollama ollama pull <llm_model>

보는 것은 두 가지다. 규칙이 못 정한 문서의 유형을 22종 코드 하나로 답하는가,
그리고 제목을 문서에 적힌 대로 옮기는가. 폐쇄망 전제(QUR.RAG.001)라 외부 API 는 없다.
"""

import httpx
import pytest

from app.ai.llm import OllamaLlm
from app.config import settings
from app.document import draft_service, structuring
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

# 단서 낱말(회의록·참석자 등)을 일부러 뺀 문서. 규칙으로는 못 정하고 모델이 읽어야 한다.
_MEETING = (
    "2026년 9월 1일 오후 2시, 진흥원 3층 소회의실.\n"
    "발주기관 담당자와 수행사 PM 이 모여 M2 범위를 논의했다.\n"
    "논의: Redmine 연동 일정, 작업 계획 갱신 주기.\n"
    "결정: 9월 12일까지 Redmine 커넥터를 붙인다.\n"
    "다음 일정: 9월 8일 같은 장소.\n"
)


def _port() -> OllamaLlm:
    return OllamaLlm(settings.ollama_base_url, settings.llm_model, settings.llm_timeout)


@live
def test_실모델은_유형을_22종_코드_하나로_답한다():
    assert not structuring.classify_type("0901.docx", _MEETING).decided  # 전제: 규칙은 못 정한다
    answer = _port().complete(
        draft_service._TYPE_SYSTEM, draft_service._llm_user("0901.docx", _MEETING)
    )
    assert structuring.parse_type_answer(answer.text) == "MEETING_RECORD", answer.text


@live
def test_실모델은_제목을_문서에서_옮긴다():
    text = "AX Link 요구사항정의서 (IM-001)\n2026년 AX 프로젝트 관리 운영 프레임워크 개발 용역\n"
    answer = _port().complete(draft_service._TITLE_SYSTEM, draft_service._llm_user("x.docx", text))
    title = structuring.parse_title_answer(answer.text)
    assert title and "요구사항정의서" in title, answer.text
