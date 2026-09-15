"""/api/conversations · /api/messages. 프런트 features/ax-query 가 부르는 경로 그대로다.

질문은 SSE 로 답한다. 프런트 lib/http.ts openStream 이 POST + Accept: text/event-stream 으로
열고 lib/sse.ts 가 event/data 줄을 읽는다.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse

from app.auth.deps import Principal
from app.common.paging import PageQuery, PageResponse
from app.db import tx
from app.rag import service
from app.rag.models import (
    AskRequest,
    ConversationCreateRequest,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageFeedbackRequest,
    MessageResponse,
    SuggestedQuestionsResponse,
)

router = APIRouter(prefix="/api", tags=["ask"])


@router.get("/conversations", response_model=PageResponse[ConversationResponse])
def list_conversations(
    principal: Principal, page: int = 0, size: int = 20
) -> PageResponse[ConversationResponse]:
    with tx() as cur:
        return service.list_conversations(cur, principal, PageQuery(page=page, size=size))


@router.get("/conversations/suggestions", response_model=SuggestedQuestionsResponse)
def suggestions(
    principal: Principal,
    projectIds: Annotated[list[str] | None, Query()] = None,  # noqa: N803 (프런트 쿼리 이름)
) -> SuggestedQuestionsResponse:
    with tx() as cur:
        return service.suggestions(cur, principal, projectIds or [])


@router.post(
    "/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    req: ConversationCreateRequest, principal: Principal
) -> ConversationResponse:
    with tx() as cur:
        return service.create_conversation(cur, principal, req)


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: str, req: ConversationUpdateRequest, principal: Principal
) -> ConversationResponse:
    with tx() as cur:
        return service.update_conversation(cur, principal, conversation_id, req)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, principal: Principal) -> Response:
    with tx() as cur:
        service.delete_conversation(cur, principal, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(conversation_id: str, principal: Principal) -> list[MessageResponse]:
    with tx() as cur:
        return service.list_messages(cur, principal, conversation_id)


@router.post("/conversations/{conversation_id}/messages")
def ask(conversation_id: str, req: AskRequest, principal: Principal) -> StreamingResponse:
    """질문 하나. 답은 SSE 스트림(start → delta… → sources → infographic → done)이다."""
    with tx() as cur:
        prepared = service.prepare(cur, principal, conversation_id, req)
    return StreamingResponse(
        service.stream(prepared),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def feedback(message_id: str, req: MessageFeedbackRequest, principal: Principal) -> Response:
    with tx() as cur:
        service.set_feedback(cur, principal, message_id, req)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
