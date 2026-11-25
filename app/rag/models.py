"""AI 질의 DTO. 프런트 types/api.ts 의 Ask·Conversation·Message·Sse 계약과 필드가 1:1 이다."""

from typing import Literal

from pydantic import BaseModel, Field

from app.semantic.models import WidgetDataResponse

RouteType = Literal[
    "DOCUMENT", "AGGREGATE", "MIXED", "OVERVIEW", "INTENT", "CLARIFY", "AI_JUDGE"
]
MessageFeedback = Literal["UP", "DOWN"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    projectScope: list[str] = Field(default_factory=list)  # noqa: N815
    # 권장 질문을 눌렀을 때 그 키. 서버가 카탈로그·권한으로 다시 검증하고 재분류하지 않는다
    hint: str | None = Field(default=None, max_length=120)


class SuggestionItem(BaseModel):
    """이어 물을 질문 하나. 문장은 서버 틀이고 hint 는 누를 때 같이 보내는 키다."""

    question: str
    hint: str


class ConversationCreateRequest(BaseModel):
    title: str | None = None
    projectScope: list[str] = Field(default_factory=list)  # noqa: N815


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    projectScope: list[str] | None = None  # noqa: N815


class ConversationResponse(BaseModel):
    id: str
    title: str
    projectScope: list[str]  # noqa: N815
    projectNames: list[str]  # noqa: N815
    pinned: bool
    messageCount: int  # noqa: N815
    lastMessageAt: str | None  # noqa: N815
    createdAt: str  # noqa: N815


class QueryRouting(BaseModel):
    type: RouteType
    rewrittenQuery: str | None  # noqa: N815
    measureKey: str | None  # noqa: N815
    dimensions: list[str]
    viz: str | None
    listing: str | None = None  # 종류 전체를 나열한 경우 그 source_type
    listingStatus: str | None = None  # noqa: N815 — 목록의 상태 조건 (OPEN | CLOSED | ALL)
    routeCached: bool = False  # noqa: N815 — 판정을 캐시에서 가져왔는가 (ARC-014)
    intent: str | None = None  # 일정 질문 묶음 키 (INTENT 일 때)


class InfographicEvent(BaseModel):
    """답변에 끼워 넣는 그림 하나 (ARC-013).

    값은 시맨틱 레이어의 집계이거나 표준 모델의 행이다. 모델은 무엇을 그릴지만 골랐다.
    slot 은 본문의 `[그림 N]` 표식 번호다. 프런트가 그 자리에 렌더러를 끼운다.
    """

    slot: int = 1
    template: str
    title: str
    data: WidgetDataResponse
    note: str | None = None  # 그림 아래 설명. 목록이면 "총 N건 중 앞 M건"


class MessageSourceResponse(BaseModel):
    footnoteNo: int  # noqa: N815
    docChunkId: str  # noqa: N815
    sourceType: str  # noqa: N815
    sourceId: str  # noqa: N815
    sourceLabel: str  # noqa: N815
    projectId: str  # noqa: N815
    projectName: str  # noqa: N815
    snippet: str
    externalUrl: str | None  # noqa: N815
    documentUrl: str | None  # noqa: N815
    pageNo: int | None  # noqa: N815
    # 원문 위치를 사람 말로(표제 경로 / 쪽 / 행). 화면은 이 문장을 그대로 보인다 (SWFR.RAG.006)
    location: str | None = None


class MessageResponse(BaseModel):
    id: str
    conversationId: str  # noqa: N815
    seq: int
    role: str
    content: str
    routing: QueryRouting | None
    sources: list[MessageSourceResponse]
    feedback: MessageFeedback | None
    createdAt: str  # noqa: N815
    infographics: list[InfographicEvent] = []
    latencyMs: int | None = None  # noqa: N815 — 답을 만드는 데 든 시간. 화면에 작게 보인다
    finishReason: str | None = None  # noqa: N815 — 답의 종류. STOP·PARTIAL·NO_DATA 등
    suggestions: list[SuggestionItem] = []


class MessageFeedbackRequest(BaseModel):
    feedback: MessageFeedback


class SuggestedQuestionsResponse(BaseModel):
    questions: list[str]


class SseStartEvent(BaseModel):
    conversationId: str  # noqa: N815
    userMessageId: str  # noqa: N815
    assistantMessageId: str  # noqa: N815
    routing: QueryRouting | None
    retrievedChunkCount: int  # noqa: N815


class SseDeltaEvent(BaseModel):
    text: str


class SseSourcesEvent(BaseModel):
    sources: list[MessageSourceResponse]


class SseSuggestionsEvent(BaseModel):
    items: list[SuggestionItem]


class SseDoneEvent(BaseModel):
    assistantMessageId: str  # noqa: N815
    finishReason: str  # noqa: N815
    elapsedMs: int  # noqa: N815
