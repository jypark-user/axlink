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
    # 서버가 알려준 용도. 없으면 null(모름)
    capabilities: list[str] | None = None
    # ANSWER 답변 모델로 쓸 수 있음 · EMBEDDING 검색(임베딩) 전용 · UNKNOWN 확인 필요
    purpose: str = "UNKNOWN"
    verifiedAt: str | None = None  # noqa: N815 — 마지막 짧은 생성 확인 성공
    # 클라우드 위임 모델(생성이 외부로 나감). 폐쇄망 배포에 맞지 않는다(UC-061, AC-061-4)
    cloud: bool = False
    remoteHost: str | None = None  # noqa: N815 — 위임 대상 주소. 로컬 모델은 null


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
    # 실제 요청에 쓰이는 값과 그 출처. DB 설정이 있으면 그것, 없으면 환경변수 기본값이다
    source: str = "DB"  # DB | ENV
    # 이 모델이 쓰이는 곳. 질문 분류와 답변 생성이 같은 모델을 쓴다
    usedFor: list[str] = []  # noqa: N815


class EmbeddingIndexModel(BaseModel):
    model: str
    chunks: int


class EmbeddingStatusResponse(BaseModel):
    """검색 모델(임베딩). 환경변수로 정해지고 화면에서는 바꾸지 않는다(ARC-022)."""

    provider: str
    baseUrl: str  # noqa: N815
    model: str
    dimension: int
    columnDimension: int | None  # noqa: N815 — doc_chunk.embedding 컬럼 차원
    source: str  # ENV
    serverHasModel: bool | None  # noqa: N815 — 서버 목록에 있는가. 확인 못 하면 null
    serverCapabilities: list[str] | None  # noqa: N815
    indexModels: list[EmbeddingIndexModel]  # noqa: N815 — 색인에 쓰인 모델과 조각 수
    consistent: bool  # 색인이 모두 지금 모델로 만들어졌는가
    message: str | None  # 맞지 않으면 그 이유. 검색·색인이 멈춰 있다
    changeBlockedReason: str  # noqa: N815 — 화면에서 바꿀 수 없는 이유


class EmbeddingUpdateRequest(BaseModel):
    model: str = Field(min_length=1)
    baseUrl: str | None = None  # noqa: N815


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
    tokPerSec: float | None  # noqa: N815  서버가 소요 시간을 안 주면 None
    evalCount: int  # noqa: N815
    evalDurationSeconds: float | None  # noqa: N815
    measuredAt: str  # noqa: N815


class AiRuntimeResponse(BaseModel):
    """질의 화면이 보이는 지금의 답변 모델. 고정 응답이면 실모델 답이 아님을 알린다."""

    llmProvider: str  # noqa: N815 — ollama | fake
    model: str | None
    fixed: bool  # 생성이나 임베딩이 고정 응답인가
    codeVersion: str | None = None  # noqa: N815 — 실행 코드 이름표(AXLINK_BUILD_LABEL)
