"""AI 질의 흐름. 대화 관리와 질문 한 건의 처리(라우팅 → 검색 → 게이트 → 생성 → 출처).

질문 처리는 세 트랜잭션으로 나뉜다. 모델 호출(라우팅·임베딩·생성)이 그 사이에 있어
DB 연결을 붙든 채 수십 초를 기다리지 않게 하려는 것이다.

  1. prepare : 대화·권한 확인, 사용자 메시지 저장. 여기서 나는 오류는 보통의 HTTP 오류다.
  2. stream  : 라우팅과 임베딩 뒤 검색·집계·답변 메시지(STREAMING) 저장, 그다음 생성.
  3. finish  : 답변 본문·상태·소요시간 확정.

메뉴 화면과 같은 semantic.run() 으로 집계하므로 두 경로의 수치가 어긋나면 그건 버그다.
"""

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.ai.embedding import embedding_port
from app.ai.llm import llm_port
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.config import settings
from app.db import tx
from app.rag import answer, blocks, entity_table, overview, route_cache, routing, search
from app.rag import conversation_repository as repo
from app.rag.models import (
    AskRequest,
    ConversationCreateRequest,
    ConversationResponse,
    ConversationUpdateRequest,
    InfographicEvent,
    MessageFeedbackRequest,
    MessageResponse,
    MessageSourceResponse,
    QueryRouting,
    SseDeltaEvent,
    SseDoneEvent,
    SseSourcesEvent,
    SseStartEvent,
    SuggestedQuestionsResponse,
)
from app.rag.search import RetrievedChunk
from app.semantic import catalog as catalog_module
from app.semantic import service as semantic
from app.semantic.catalog import Catalog
from app.semantic.models import WidgetOptions, WidgetQuery, WidgetSpec

log = logging.getLogger(__name__)

DEFAULT_TITLE = "새 대화"
MAX_TITLE = 200

# 추천 질문에 쓰는 지표. 카탈로그에 있는 것만 문장으로 만든다.
_SUGGESTED_MEASURES = (
    "progress_representative_pct",
    "requirement_fulfillment_rate",
    "open_issue_count",
    "work_product_approval_rate",
)
_SUGGESTED_DOCUMENT_QUESTIONS = (
    "과업지시서에 정한 납품 산출물은 무엇인가요?",
    "최근 이슈에서 지연 사유로 적힌 내용은 무엇인가요?",
)


# ---------------------------------------------------------------- 대화


def list_conversations(
    cur: Any, principal: AuthPrincipal, query: PageQuery
) -> PageResponse[ConversationResponse]:
    rows = repo.list_conversations(cur, principal.user_id, query.size, query.offset)
    total = repo.count_conversations(cur, principal.user_id)
    return PageResponse.of([_conversation(r) for r in rows], query, total)


def create_conversation(
    cur: Any, principal: AuthPrincipal, req: ConversationCreateRequest
) -> ConversationResponse:
    scope = _scope(_allowed(cur, principal), req.projectScope, require=False)
    title = (req.title or "").strip()[:MAX_TITLE] or DEFAULT_TITLE
    return _conversation(repo.insert_conversation(cur, principal.user_id, title, scope))


def update_conversation(
    cur: Any, principal: AuthPrincipal, conversation_id: str, req: ConversationUpdateRequest
) -> ConversationResponse:
    _own(cur, principal, conversation_id)
    title = req.title.strip()[:MAX_TITLE] if req.title is not None else None
    if title == "":
        raise errors.validation_failed("제목이 비어 있습니다.")
    scope = None
    if req.projectScope is not None:
        scope = _scope(_allowed(cur, principal), req.projectScope, require=False)
    repo.update_conversation(cur, conversation_id, title, req.pinned, scope)
    return _conversation(_own(cur, principal, conversation_id))


def delete_conversation(cur: Any, principal: AuthPrincipal, conversation_id: str) -> None:
    _own(cur, principal, conversation_id)
    repo.delete_conversation(cur, conversation_id)


def list_messages(
    cur: Any, principal: AuthPrincipal, conversation_id: str
) -> list[MessageResponse]:
    _own(cur, principal, conversation_id)
    rows = repo.list_messages(cur, conversation_id)
    sources: dict[str, list[MessageSourceResponse]] = {}
    for s in repo.sources_for_messages(cur, [r["id"] for r in rows]):
        sources.setdefault(s["message_id"], []).append(_source(s))
    return [_message(r, sources.get(r["id"], [])) for r in rows]


def set_feedback(
    cur: Any, principal: AuthPrincipal, message_id: str, req: MessageFeedbackRequest
) -> None:
    owner = repo.message_owner(cur, message_id)
    if owner is None or owner["user_id"] != principal.user_id or owner["role"] != "ASSISTANT":
        raise errors.not_found("메시지", message_id)
    repo.set_feedback(cur, message_id, req.feedback)


def suggestions(
    cur: Any, principal: AuthPrincipal, project_ids: list[str]
) -> SuggestedQuestionsResponse:
    """추천 질문. 카탈로그 지표 라벨에서 만든다. 사업 범위는 접근 확인에만 쓴다."""
    _scope(_allowed(cur, principal), project_ids, require=False)
    catalog = catalog_module.load(cur)
    questions = [
        f"{m.label}은(는) 현재 얼마인가요?"
        for key in _SUGGESTED_MEASURES
        if (m := catalog.measure(key)) is not None
    ]
    questions.extend(_SUGGESTED_DOCUMENT_QUESTIONS)
    return SuggestedQuestionsResponse(questions=questions)


# ---------------------------------------------------------------- 질문


@dataclass
class Prepared:
    principal: AuthPrincipal
    conversation_id: str
    question: str
    scope: list[str]
    user_message_id: str
    catalog: Catalog
    started: float


def prepare(cur: Any, principal: AuthPrincipal, conversation_id: str, req: AskRequest) -> Prepared:
    """스트림을 열기 전에 끝내야 하는 것. 여기서 실패하면 보통의 오류 응답이 나간다."""
    question = " ".join(req.question.split())
    if not question:
        raise errors.validation_failed("question 이 비어 있습니다.")
    conversation = _own(cur, principal, conversation_id)
    allowed = _allowed(cur, principal)
    requested = req.projectScope or list(conversation["project_scope"] or [])
    scope = _scope(allowed, requested, require=True)

    seq = repo.next_seq(cur, conversation_id)
    user_message_id = repo.insert_message(cur, conversation_id, seq, "USER", question)
    repo.touch_conversation(cur, conversation_id)
    return Prepared(
        principal=principal,
        conversation_id=conversation_id,
        question=question,
        scope=scope,
        user_message_id=user_message_id,
        catalog=catalog_module.load(cur),
        started=time.monotonic(),
    )


def stream(p: Prepared) -> Iterator[bytes]:
    """SSE 이벤트 순서: start → delta… → sources → (infographic) → done. 오류는 error 하나."""
    assistant_id: str | None = None
    pieces: list[str] = []
    try:
        llm = llm_port()
        # 판정은 캐시를 먼저 본다(ARC-014). 값은 아래에서 매번 새로 뽑는다.
        with tx() as cur:
            routed = route_cache.decide(cur, p.catalog, llm, p.question)
        decision = routed.decision
        query_text = decision.rewritten or p.question
        query_vec = embedding_port().embed([p.question])[0]

        with tx() as cur:
            aggregate: answer.AggregateContext | None = None
            block_list: list[blocks.Block] = []
            if decision.type == routing.AGGREGATE:
                aggregate, infographic = _aggregate(cur, p, decision)
                if aggregate is None:
                    decision = routing.RouteDecision(
                        type=routing.DOCUMENT,
                        rewritten=decision.rewritten,
                        listing=decision.listing,
                        listing_status=decision.listing_status,
                    )
                elif infographic is not None and blocks.worth_drawing(infographic.data):
                    # 값이 하나뿐이면 문장이 그 숫자를 말한다. 그림은 붙이지 않는다. 값은
                    # aggregate 로 프롬프트와 수치 검문에 그대로 들어간다(ARC-013 4-1).
                    block_list.append(
                        blocks.from_aggregate(
                            len(block_list) + 1,
                            infographic.template,
                            infographic.title,
                            infographic.data,
                            aggregate.lines,
                        )
                    )
            # 목록은 표준 모델에서 행을 꺼내 표로 그린다. 청크에는 상태가 없어 조건을 못 건다
            # (ARC-013). 09.17 실측에서 닫힌 이슈가 "작업이 안 된" 목록에 섞였다.
            table = None
            if decision.listing:
                entity = entity_table.FROM_SOURCE_TYPE.get(decision.listing)
                table = (
                    entity_table.build(
                        cur, entity, decision.listing_status, p.scope, settings.rag_list_limit
                    )
                    if entity
                    else None
                )
                if table is not None:
                    block_list.append(blocks.from_entity(len(block_list) + 1, table))

            # 사업 현황을 묻는 질문은 현황 그림으로 답한다(ARC-015)
            used_overview = False
            if decision.type == routing.OVERVIEW:
                block_list.extend(overview.build(cur, p.principal, p.scope, len(block_list) + 1))
                used_overview = bool(block_list)

            # 근거를 어디서 찾을지. 표를 만들었으면 같은 목록을 청크로 또 넣지 않는다. 09.17
            # 실측에서 요구사항 41건이 표와 청크 양쪽으로 들어가 프롬프트가 불어나 모델이
            # 시간 초과로 끊겼다. 표가 답이고, 청크는 주제가 닿는 것만 출처로 붙인다.
            if decision.listing and table is None:
                found = search.list_by_source(
                    cur,
                    decision.listing,
                    p.scope,
                    settings.rag_list_limit,
                    settings.rag_list_chars,
                )
            else:
                found = search.search_with_vector(cur, query_vec, query_text, p.scope)

            gate_ok = found.passes_gate()
            chunks = found.chunks if gate_ok else []
            # 무관하다고 했는데 문서 근거가 실제로 있으면 문서 질문이다. 모델이 "인수 조건이
            # 뭐야" 를 무관으로 본 사례가 있어, 근거가 판정을 이긴다(ARC-015 3-3).
            if decision.type == routing.OFF_TOPIC and gate_ok:
                decision = routing.RouteDecision(
                    type=routing.DOCUMENT, rewritten=decision.rewritten
                )
            # 근거도 그림도 없으면 현황으로 내려간다. "답을 만들지 않았다" 보다 "맞는 문서는 없지만
            # 지금 상태는 이렇다" 가 낫다. 데이터가 아예 없는 사업에서만 예전처럼 막는다.
            used_fallback = False
            if (
                decision.type == routing.DOCUMENT
                and not gate_ok
                and not block_list
                and settings.rag_overview_fallback
            ):  # OFF_TOPIC 은 여기 오지 않는다. 무관한 질문에 현황을 내지 않는다
                block_list.extend(overview.build(cur, p.principal, p.scope, 1))
                used_fallback = bool(block_list)
            route_type = _route_type(decision.type, gate_ok)
            if used_overview or used_fallback:
                route_type = routing.OVERVIEW
            routing_info = QueryRouting(
                type=route_type,
                rewrittenQuery=decision.rewritten,
                measureKey=decision.measure.key if decision.measure else None,
                dimensions=list(decision.dimensions),
                viz=block_list[0].template if block_list else None,
                listing=decision.listing,
                listingStatus=decision.listing_status if decision.listing else None,
                routeCached=routed.cached,
            )
            assistant_id = repo.insert_message(
                cur,
                p.conversation_id,
                repo.next_seq(cur, p.conversation_id),
                "ASSISTANT",
                "",
                status="STREAMING",
                route_type=route_type,
                rewritten_query=decision.rewritten,
                measure_key=routing_info.measureKey,
                infographic=[b.as_event() for b in block_list] or None,
            )
            repo.insert_sources(
                cur, assistant_id, [_source_row(i, c) for i, c in enumerate(chunks, 1)]
            )
            repo.touch_conversation(cur, p.conversation_id)

        yield _sse(
            "start",
            SseStartEvent(
                conversationId=p.conversation_id,
                userMessageId=p.user_message_id,
                assistantMessageId=assistant_id,
                routing=routing_info,
                retrievedChunkCount=len(chunks),
            ),
        )

        if used_fallback:
            # 서버가 첫 줄을 쓴다. 문서를 못 찾았다는 말은 모델에게 맡기지 않는다
            pieces.append(overview.LEAD)
            yield _sse("delta", SseDeltaEvent(text=overview.LEAD))
        if decision.type == routing.OFF_TOPIC:
            # 사업과 무관한 질문. 현황으로 내려가면 날씨를 물었는데 진척률이 나온다
            text = answer.off_topic()
            pieces.append(text)
            yield _sse("delta", SseDeltaEvent(text=text))
            finish_reason = "NO_EVIDENCE"
        elif decision.type == routing.DOCUMENT and not gate_ok and not block_list:
            # 근거 게이트(SWFR.RAG.007). 모델을 부르지 않는다.
            # 표가 만들어졌으면 근거가 있는 것이다. 표준 모델에서 꺼낸 행이라 색인이 비어
            # 있어도 답할 수 있다(ARC-013). 청크 유사도만으로 막으면 될 답을 막는다.
            if decision.listing:
                text = answer.empty_listing(routing.LISTABLE[decision.listing])
            else:
                text = answer.insufficient_evidence(found.max_similarity, found.candidate_count)
            pieces.append(text)
            yield _sse("delta", SseDeltaEvent(text=text))
            finish_reason = "NO_EVIDENCE"
        else:
            scope_line = None
            # 표를 만들었으면 범위는 표의 설명이 말한다. 두 번 말하면 모델이 둘을 더한다.
            if decision.listing and decision.type == routing.DOCUMENT and table is None:
                scope_line = answer.listing_scope(
                    routing.LISTABLE[decision.listing], len(chunks), found.candidate_count
                )
            prompt = answer.user_prompt(p.question, chunks, aggregate, scope_line, block_list)
            raw = llm.stream(answer.SYSTEM_PROMPT, prompt, json_schema=answer.ANSWER_SCHEMA)
            for piece in answer.decode_answer(answer.strip_think(raw)):
                pieces.append(piece)
                yield _sse("delta", SseDeltaEvent(text=piece))
            # 본문이 표식을 안 쓴 그림은 끝에 붙인다. 만든 그림을 조용히 버리지 않는다.
            tail = blocks.append_missing("".join(pieces), block_list)
            if tail:
                pieces.append(tail)
                yield _sse("delta", SseDeltaEvent(text=tail))
            finish_reason = "STOP"
            grounds = [p.question, *(c.content for c in chunks)]
            if scope_line:
                grounds.append(scope_line)
            if aggregate is not None:
                grounds.extend(aggregate.lines)
            for block in block_list:
                grounds.extend(block.lines)
                if block.note:
                    grounds.append(block.note)
            bad = answer.ungrounded_numbers("".join(pieces), grounds)
            if bad:
                # 지시를 어기고 만든 숫자는 지우지 못한다(이미 화면에 나갔다). 표시하고 남긴다.
                note = answer.guard_note(bad)
                pieces.append(note)
                yield _sse("delta", SseDeltaEvent(text=note))
                finish_reason = "NUMBER_GUARD"

        sources = [_source_from_chunk(i, c) for i, c in enumerate(chunks, 1)]
        yield _sse("sources", SseSourcesEvent(sources=sources))
        for block in block_list:
            yield _sse_raw("infographic", block.as_event())

        elapsed = _elapsed(p)
        with tx() as cur:
            repo.finish_message(cur, assistant_id, "".join(pieces).strip(), "COMPLETE", elapsed)
            # 답을 만든 판정만 다음에 다시 쓴다. 근거가 없어 막히거나 현황으로 내려간 판정은
            # 틀렸을 수 있다(ARC-014).
            if finish_reason != "NO_EVIDENCE" and not used_fallback:
                route_cache.remember(cur, p.question, routed)
        done = SseDoneEvent(
            assistantMessageId=assistant_id, finishReason=finish_reason, elapsedMs=elapsed
        )
        yield _sse("done", done)
    except GeneratorExit:
        _abort(assistant_id, pieces, p)
        raise
    except errors.ApiError as exc:
        _abort(assistant_id, pieces, p)
        yield _sse_raw("error", {"code": exc.code, "message": exc.message})
    except Exception:
        log.exception("질의 처리 실패 conversation=%s", p.conversation_id)
        _abort(assistant_id, pieces, p)
        yield _sse_raw("error", {"code": "INTERNAL", "message": "답변 생성 중 오류가 났습니다."})


def _aggregate(
    cur: Any, p: Prepared, decision: routing.RouteDecision
) -> tuple[answer.AggregateContext | None, InfographicEvent | None]:
    """모델이 고른 지표·차원·템플릿으로 시맨틱 레이어를 돌린다. 카탈로그 검증에서
    막히면 집계를 포기한다. 값을 억지로 만들지 않는다."""
    assert decision.measure is not None and decision.template is not None
    spec = WidgetSpec(
        template=decision.template,
        title=decision.title,
        query=WidgetQuery(
            measure=decision.measure.key,
            dimensions=list(decision.dimensions),
            filters=[],
            projectScope=list(p.scope),
        ),
        options=WidgetOptions(sort="desc"),
    )
    try:
        data = semantic.run(cur, p.principal, spec)
    except errors.ApiError as exc:
        if exc.code == "CATALOG_VALIDATION_FAILED":
            return None, None
        raise
    infographic = InfographicEvent(template=decision.template, title=decision.title, data=data)
    return answer.AggregateContext.of(decision.title, data), infographic


def _route_type(decided: str, gate_ok: bool) -> str:
    if decided == routing.AGGREGATE:
        return routing.MIXED if gate_ok else routing.AGGREGATE
    return routing.DOCUMENT


def _abort(assistant_id: str | None, pieces: list[str], p: Prepared) -> None:
    if assistant_id is None:
        return
    try:
        with tx() as cur:
            repo.finish_message(cur, assistant_id, "".join(pieces).strip(), "ABORTED", _elapsed(p))
    except Exception:
        log.exception("답변 중단 기록 실패 message=%s", assistant_id)


def _elapsed(p: Prepared) -> int:
    return int((time.monotonic() - p.started) * 1000)


# ---------------------------------------------------------------- 권한·범위


def _allowed(cur: Any, principal: AuthPrincipal) -> list[str]:
    return auth_repo.allowed_project_ids(cur, principal.role, principal.org_id, principal.user_id)


def _scope(allowed: list[str], requested: list[str], require: bool) -> list[str]:
    """요청 범위와 접근 가능 범위의 교집합(SER.SEC.003). require 면 빈 범위는 거절한다."""
    if not requested:
        if require and not allowed:
            raise errors.project_access_denied()
        return list(allowed) if require else []
    scope = [pid for pid in requested if pid in allowed]
    if len(scope) != len(requested):
        raise errors.project_access_denied()
    return scope


def _own(cur: Any, principal: AuthPrincipal, conversation_id: str) -> dict[str, Any]:
    row = repo.get_conversation(cur, conversation_id, principal.user_id)
    if row is None:
        raise errors.not_found("대화", conversation_id)
    return row


# ---------------------------------------------------------------- 응답 조립


def _conversation(row: dict[str, Any]) -> ConversationResponse:
    return ConversationResponse(
        id=row["id"],
        title=row["title"],
        projectScope=list(row["project_scope"] or []),
        projectNames=list(row["project_names"] or []),
        pinned=bool(row["pinned"]),
        messageCount=int(row["message_count"]),
        lastMessageAt=_iso(row["last_message_at"]),
        createdAt=_iso(row["created_at"]) or "",
    )


def _message(row: dict[str, Any], sources: list[MessageSourceResponse]) -> MessageResponse:
    raw = row["infographic_json"]
    # V28 이전 메시지는 그림 하나를 객체로 담고 있다. 목록으로 펴서 같은 길로 읽는다.
    items = raw if isinstance(raw, list) else [raw] if raw else []
    infographics = [InfographicEvent.model_validate(item) for item in items]
    first = infographics[0] if infographics else None
    routing_info = None
    if row["route_type"]:
        routing_info = QueryRouting(
            type=row["route_type"],
            rewrittenQuery=row["rewritten_query"],
            measureKey=row["measure_key"],
            dimensions=list(first.data.dimensions) if first else [],
            viz=first.template if first else None,
        )
    return MessageResponse(
        id=row["id"],
        conversationId=row["conversation_id"],
        seq=int(row["seq"]),
        role=row["role"],
        content=row["content"],
        routing=routing_info,
        sources=sources,
        feedback=row["feedback"],
        createdAt=_iso(row["created_at"]) or "",
        infographics=infographics,
        latencyMs=row.get("latency_ms"),
    )


def _source_row(footnote_no: int, chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "footnote_no": footnote_no,
        "doc_chunk_id": chunk.id,
        "source_type": chunk.source_type,
        "source_title": chunk.source_title[:500],
        "snippet": answer.snippet(chunk),
        # 컬럼이 not null 이다. 업로드 문서의 저장 경로는 링크가 아니라 비워 둔다.
        "external_url": chunk.source_uri if _is_url(chunk.source_uri) else "",
        "page_no": chunk.page_no,
    }


def _source_from_chunk(footnote_no: int, chunk: RetrievedChunk) -> MessageSourceResponse:
    return MessageSourceResponse(
        footnoteNo=footnote_no,
        docChunkId=chunk.id,
        sourceType=chunk.source_type,
        sourceId=chunk.source_id,
        sourceLabel=chunk.source_title,
        projectId=chunk.project_id,
        projectName=chunk.project_name,
        snippet=answer.snippet(chunk),
        externalUrl=chunk.source_uri if _is_url(chunk.source_uri) else None,
        documentUrl=_document_url(chunk.source_type, chunk.project_id),
        pageNo=chunk.page_no,
    )


def _source(row: dict[str, Any]) -> MessageSourceResponse:
    project_id = row["project_id"] or ""
    return MessageSourceResponse(
        footnoteNo=int(row["footnote_no"]),
        docChunkId=row["doc_chunk_id"] or "",
        sourceType=row["source_type"],
        sourceId=row["source_id"] or "",
        sourceLabel=row["source_title"],
        projectId=project_id,
        projectName=row["project_name"] or "",
        snippet=row["snippet"],
        externalUrl=row["external_url"] if _is_url(row["external_url"]) else None,
        documentUrl=_document_url(row["source_type"], project_id),
        pageNo=row["page_no"],
    )


def _document_url(source_type: str, project_id: str) -> str | None:
    """업로드 문서는 외부 링크가 없다. 화면의 문서 목록으로 보낸다."""
    if source_type == "DOCUMENT_UPLOAD" and project_id:
        return f"/p/{project_id}/documents"
    return None


def _is_url(value: str | None) -> bool:
    return bool(value) and value.startswith(("http://", "https://"))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _sse(event: str, payload: BaseModel) -> bytes:
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n".encode()


def _sse_raw(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
