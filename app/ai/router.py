"""/api/ai/* — LLM 모델 설정 (ARC-011). 설정은 플랫폼 관리자만, 지금 모델 확인은 누구나.

모델 목록 조회는 저장 전에 즉시 부른다. 사용자가 주소를 입력하는 동안 프런트가 디바운스로
부르므로 실패는 200 + error 문구다. 예외를 올리면 한 글자마다 오류 대화상자가 뜬다.
"""

from fastapi import APIRouter, Query

from app.ai import answer_mode, model_settings
from app.ai.models import (
    AiRuntimeResponse,
    AnswerModeResponse,
    AnswerModeUpdateRequest,
    EmbeddingStatusResponse,
    EmbeddingUpdateRequest,
    LlmMeasureResponse,
    LlmModelListResponse,
    LlmModelParamsUpdateRequest,
    LlmModelResponse,
    LlmSettingResponse,
    LlmSettingUpdateRequest,
)
from app.auth.deps import Principal
from app.config import settings
from app.db import tx

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/runtime", response_model=AiRuntimeResponse)
def runtime(principal: Principal) -> AiRuntimeResponse:
    """로그인한 누구나. 주소는 내보내지 않고 공급자와 모델 이름만."""
    fixed = settings.llm_provider == "fake" or settings.embedding_provider == "fake"
    model = None
    if settings.llm_provider != "fake":
        with tx() as cur:
            model = model_settings.runtime_config(cur).model
    return AiRuntimeResponse(
        llmProvider=settings.llm_provider,
        model=model,
        fixed=fixed,
        codeVersion=settings.build_label,
    )


@router.get("/answer-mode", response_model=AnswerModeResponse)
def get_answer_mode(principal: Principal) -> AnswerModeResponse:
    """답변 방식(ARC-034). 로그인한 누구나 읽는다. 질의 화면이 지금 방식을 보인다."""
    with tx() as cur:
        return answer_mode.get(cur)


@router.put("/answer-mode", response_model=AnswerModeResponse)
def put_answer_mode(req: AnswerModeUpdateRequest, principal: Principal) -> AnswerModeResponse:
    with tx() as cur:
        return answer_mode.save(cur, principal, req)


@router.get("/settings", response_model=LlmSettingResponse)
def get_settings(principal: Principal) -> LlmSettingResponse:
    with tx() as cur:
        return model_settings.get_setting(cur, principal)


@router.put("/settings", response_model=LlmSettingResponse)
def put_settings(req: LlmSettingUpdateRequest, principal: Principal) -> LlmSettingResponse:
    with tx() as cur:
        return model_settings.save_setting(cur, principal, req)


@router.get("/embedding", response_model=EmbeddingStatusResponse)
def get_embedding(principal: Principal) -> EmbeddingStatusResponse:
    """검색 모델 현황과 색인 모델. 관리자가 검색이 멈춘 원인을 여기서 본다."""
    with tx() as cur:
        return model_settings.embedding_status(cur, principal)


@router.put("/embedding")
def put_embedding(req: EmbeddingUpdateRequest, principal: Principal) -> None:
    """검색 모델은 화면에서 바꾸지 않는다. 안전한 재색인이 생기기 전까지 409."""
    model_settings.reject_embedding_change(principal)


@router.post("/models/refresh", response_model=LlmModelListResponse)
def refresh_models(
    principal: Principal, baseUrl: str = Query(default="")  # noqa: N803 (프런트 쿼리 이름)
) -> LlmModelListResponse:
    with tx() as cur:
        return model_settings.refresh_models(cur, principal, baseUrl)


@router.post("/models/measure", response_model=LlmMeasureResponse)
def measure(
    principal: Principal,
    baseUrl: str = Query(),  # noqa: N803
    model: str = Query(),
) -> LlmMeasureResponse:
    with tx() as cur:
        return model_settings.measure(cur, principal, baseUrl, model)


@router.put("/models/params", response_model=LlmModelResponse)
def update_params(
    req: LlmModelParamsUpdateRequest,
    principal: Principal,
    baseUrl: str = Query(),  # noqa: N803
    model: str = Query(),
) -> LlmModelResponse:
    with tx() as cur:
        return model_settings.update_params(cur, principal, baseUrl, model, req)
