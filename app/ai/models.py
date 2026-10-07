"""AI 설정 DTO. 필드명은 프런트 types/api.ts 계약과 1:1 이다 (ARC-011)."""

from pydantic import BaseModel, Field


class LlmModelResponse(BaseModel):
    name: str
    baseUrl: str  # noqa: N815 — 프런트 계약 필드명
    contextLength: int  # noqa: N815 — 서버가 안 알려주면 0
    supportsTools: bool  # noqa: N815
    parameterSize: str | None  # noqa: N815
    quantization: str | None
    tokPerSec: float | None  # noqa: N815 — 미측정이면 null
    measuredAt: str | None  # noqa: N815
    numCtx: int | None  # noqa: N815
    numPredict: int  # noqa: N815
    fetchedAt: str  # noqa: N815


class LlmModelListResponse(BaseModel):
    baseUrl: str  # noqa: N815
    models: list[LlmModelResponse]
    error: str | None = None  # 조회 실패는 예외가 아니라 상태 문구다


class LlmSettingResponse(BaseModel):
    baseUrl: str  # noqa: N815
    model: str
    provider: str
    # 한 요청이 쓸 수 있는 초. 권장값 계산의 limit 이다. 0 이면 미설정.
    requestTimeoutSeconds: float  # noqa: N815
    updatedAt: str | None  # noqa: N815
    models: list[LlmModelResponse]


class LlmSettingUpdateRequest(BaseModel):
    baseUrl: str = Field(min_length=1)  # noqa: N815
    model: str = Field(min_length=1)
    numCtx: int | None = Field(default=None, gt=0)  # noqa: N815
    numPredict: int = Field(default=16000, gt=0)  # noqa: N815


class LlmModelParamsUpdateRequest(BaseModel):
    numCtx: int | None = Field(default=None, gt=0)  # noqa: N815
    numPredict: int = Field(gt=0)  # noqa: N815


class LlmMeasureResponse(BaseModel):
    model: str
    tokPerSec: float  # noqa: N815
    evalCount: int  # noqa: N815
    evalDurationSeconds: float  # noqa: N815
    measuredAt: str  # noqa: N815


class AiRuntimeResponse(BaseModel):
    """질의 화면이 보이는 지금의 답변 모델. 고정 응답이면 실모델 답이 아님을 알린다."""

    llmProvider: str  # noqa: N815 — ollama | fake
    model: str | None
    fixed: bool  # 생성이나 임베딩이 고정 응답인가
    codeVersion: str | None = None  # noqa: N815 — 실행 코드 이름표(AXLINK_BUILD_LABEL)
