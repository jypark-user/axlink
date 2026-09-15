"""AI 질의 DTO. 프런트 types/api.ts 의 Ask·Conversation·Message·Sse 계약과 필드가 1:1 이다."""

from typing import Literal

from pydantic import BaseModel, Field

from app.semantic.models import WidgetDataResponse

RouteType = Literal["DOCUMENT", "AGGREGATE", "MIXED"]
MessageFeedback = Literal["UP", "DOWN"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    projectScope: list[str] = Field(default_factory=list)  # noqa: N815


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


class InfographicEvent(BaseModel):
    """값은 시맨틱 레이어가 DB 에서 뽑는다. 모델은 지표·차원·템플릿만 골랐다."""

    template: str
    title: str
    data: WidgetDataResponse


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
    infographic: InfographicEvent | None


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


class SseDoneEvent(BaseModel):
    assistantMessageId: str  # noqa: N815
    finishReason: str  # noqa: N815
    elapsedMs: int  # noqa: N815
