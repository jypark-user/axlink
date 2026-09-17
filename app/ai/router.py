"""/api/ai/* — LLM 모델 설정 (ARC-011). 플랫폼 관리자만 쓴다.

모델 목록 조회는 저장 전에 즉시 부른다. 사용자가 주소를 입력하는 동안 프런트가 디바운스로
부르므로 실패는 200 + error 문구다. 예외를 올리면 한 글자마다 오류 대화상자가 뜬다.
"""

from fastapi import APIRouter, Query

from app.ai import model_settings
from app.ai.models import (
    LlmMeasureResponse,
    LlmModelListResponse,
    LlmModelParamsUpdateRequest,
    LlmModelResponse,
    LlmSettingResponse,
    LlmSettingUpdateRequest,
)
from app.auth.deps import Principal
from app.db import tx

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/settings", response_model=LlmSettingResponse)
def get_settings(principal: Principal) -> LlmSettingResponse:
    with tx() as cur:
        return model_settings.get_setting(cur, principal)


@router.put("/settings", response_model=LlmSettingResponse)
def put_settings(req: LlmSettingUpdateRequest, principal: Principal) -> LlmSettingResponse:
    with tx() as cur:
        return model_settings.save_setting(cur, principal, req)


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
