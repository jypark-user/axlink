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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.ai import embedding_guard
from app.ai.embedding import embedding_port
from app.ai.llm import llm_port
from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.common import errors
from app.common.paging import PageQuery, PageResponse
from app.config import settings
from app.db import tx
from app.rag import (
    answer,
    blocks,
    changes,
    collection,
    entity_table,
    intents,
    lookup,
    milestones,
    number_guard,
    overview,
    question_period,
    route_cache,
    routing,
    search,
    suggest,
)
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
    SseSuggestionsEvent,
    SuggestedQuestionsResponse,
    SuggestionItem,
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
    "deliverable_approval_rate",
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
        suggest.measure_question(m)
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
    # 최근 질문·답. 후속 질문이 무엇을 가리키는지 판정과 본문이 같이 본다
    previous: list[routing.PreviousTurn] = field(default_factory=list)
    # 권장 질문을 눌렀으면 그 키. 재분류하지 않고 이 대상으로 바로 답한다
    target: routing.Target | None = None


def prepare(cur: Any, principal: AuthPrincipal, conversation_id: str, req: AskRequest) -> Prepared:
    """스트림을 열기 전에 끝내야 하는 것. 여기서 실패하면 보통의 오류 응답이 나간다."""
    question = " ".join(req.question.split())
    if not question:
        raise errors.validation_failed("question 이 비어 있습니다.")
    conversation = _own(cur, principal, conversation_id)
    allowed = _allowed(cur, principal)
    requested = req.projectScope or list(conversation["project_scope"] or [])
    scope = _scope(allowed, requested, require=True)
    catalog = catalog_module.load(cur)
    target = None
    if req.hint is not None:
        # 눌린 권장 질문의 키. 화면이 보낸 값을 믿지 않고 카탈로그로 다시 검증한다
        target = routing.parse_key(catalog, req.hint)
        if target is None:
            raise errors.validation_failed("권장 질문의 대상이 올바르지 않습니다.")

    previous = [
        routing.PreviousTurn(
            question=t["question"],
            answer=t["answer"],
            measure_key=t.get("measure_key"),
            route_type=t.get("route_type"),
            topic=t.get("rewritten_query"),
        )
        for t in repo.last_turns(cur, conversation_id, routing.PREVIOUS_TURNS)
    ]
    seq = repo.next_seq(cur, conversation_id)
    user_message_id = repo.insert_message(cur, conversation_id, seq, "USER", question)
    repo.touch_conversation(cur, conversation_id)
    return Prepared(
        principal=principal,
        conversation_id=conversation_id,
        question=question,
        scope=scope,
        user_message_id=user_message_id,
        catalog=catalog,
        started=time.monotonic(),
        previous=previous,
        target=target,
    )


def stream(p: Prepared) -> Iterator[bytes]:
    """SSE 이벤트 순서: start → delta… → sources → (infographic) → (suggestions) → done.
    오류는 error 하나. 답의 종류는 done 의 finishReason 이 말한다."""
    assistant_id: str | None = None
    pieces: list[str] = []
    try:
        llm = llm_port()
        if p.target is not None:
            # 권장 질문을 눌렀다. 키는 prepare 가 검증했다. 다시 분류하지 않는다
            routed = route_cache.Routed(routing.from_target(p.target, p.question), cached=False)
        else:
            # 판정은 캐시를 먼저 본다(ARC-014). 값은 아래에서 매번 새로 뽑는다.
            with tx() as cur:
                routed = route_cache.decide(cur, p.catalog, llm, p.question, p.previous)
        decision = routed.decision
        query_text = decision.rewritten or p.question
        # 일정 질문은 표준 모델과 WBS 로 답한다. 문서 검색은 지연 사유만 쓴다
        searches = decision.type != routing.INTENT or decision.intent == intents.DELAY_CAUSE
        query_vec = embedding_port().embed([p.question])[0] if searches else None

        with tx() as cur:
            turn = _Turn(decision=decision)
            _resolve(cur, p, turn, query_vec, query_text)
            decision = turn.decision
            chunks = turn.chunks
            route_type = _route_type(turn)
            routing_info = QueryRouting(
                type=route_type,
                rewrittenQuery=decision.rewritten,
                measureKey=decision.measure.key if decision.measure else None,
                dimensions=list(decision.dimensions),
                viz=turn.block_list[0].template if turn.block_list else None,
                listing=decision.listing,
                listingStatus=decision.listing_status if decision.listing else None,
                routeCached=routed.cached,
                intent=decision.intent if decision.type == routing.INTENT else None,
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
                infographic=[b.as_event() for b in turn.block_list] or None,
                suggestions=[s.model_dump() for s in turn.suggestions] or None,
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

        if turn.reason is not None:
            # 모델을 부르지 않는 답. 근거 게이트(SWFR.RAG.007)·값 없음·되묻기·조회 오류
            text = turn.text or ""
            pieces.append(text)
            yield _sse("delta", SseDeltaEvent(text=text))
            finish_reason = turn.reason
        else:
            scope_line = None
            # 표를 만들었으면 범위는 표의 설명이 말한다. 두 번 말하면 모델이 둘을 더한다.
            if decision.listing and decision.type == routing.DOCUMENT and turn.table is None:
                scope_line = answer.listing_scope(
                    routing.LISTABLE[decision.listing], len(chunks), turn.found_count
                )
            # 후속 질문에만 앞 대화를 준다. 주제가 선 질문에 앞 답을 주면 모델이 그걸 다시 말한다
            previous = p.previous if decision.follow_up else []
            intent = turn.intent
            values = None
            if intent is not None and intent.table is None and intent.lines:
                values = (intent.title, intent.lines)
            prompt = answer.user_prompt(
                p.question, chunks, turn.aggregate, scope_line, turn.block_list, previous, values
            )
            # 수치 검문(QUR.RAG.002, ARC-017). 숫자가 든 문장은 검사를 통과해야 나간다.
            gate = number_guard.SentenceGate(
                number_guard.Checker(
                    _facts(turn.aggregate, turn.block_list, chunks, scope_line, intent),
                    question=p.question,
                    subjects=_subjects(turn.aggregate, turn.block_list, intent),
                )
            )
            model_down = False
            try:
                raw = llm.stream(
                    answer.SYSTEM_PROMPT, prompt, json_schema=answer.ANSWER_SCHEMA
                )
                for piece in answer.decode_answer(answer.strip_think(raw)):
                    text = gate.feed(piece)
                    if text:
                        pieces.append(text)
                        yield _sse("delta", SseDeltaEvent(text=text))
            except errors.ApiError as exc:
                # 판정 캐시를 타면 판정 단계에서 장애를 모른 채 여기까지 온다(DEF-V041).
                # 집계 값이 이미 있으면 서버 문안으로 답한다. 모델 문장은 하나도 내보내지 않았다
                fallback = _model_down_answer(turn) if not pieces else None
                if exc.code != "AI_UNAVAILABLE" or fallback is None:
                    raise
                log.warning(
                    "답 생성 중 모델 서버 장애, 집계 값으로 답함 conversation=%s: %s",
                    p.conversation_id, exc.message,
                )
                model_down = True
                pieces.append(fallback)
                yield _sse("delta", SseDeltaEvent(text=fallback))
            text = "" if model_down else gate.finish()
            if text:
                pieces.append(text)
                yield _sse("delta", SseDeltaEvent(text=text))
            # 값의 성격(추정)과 부분 답의 못 한 부분은 서버 문안이 말한다. 모델에게 맡기지 않는다
            for extra in (turn.footnote, turn.notice):
                if extra:
                    text = "\n\n" + extra
                    pieces.append(text)
                    yield _sse("delta", SseDeltaEvent(text=text))
            # 본문이 표식을 안 쓴 그림은 끝에 붙인다. 만든 그림을 조용히 버리지 않는다.
            tail = blocks.append_missing("".join(pieces), turn.block_list)
            if tail:
                pieces.append(tail)
                yield _sse("delta", SseDeltaEvent(text=tail))
            finish_reason = PARTIAL if turn.notice else STOP
            if model_down:
                finish_reason = MODEL_DOWN
            elif gate.blocked:
                # 막힌 문장은 화면에도 저장 본문에도 없다. 무엇이 왜 막혔는지만 남긴다
                finish_reason = NUMBER_GUARD
                log.info(
                    "수치 검문이 문장 %d개를 막았다: %s",
                    gate.blocked,
                    ", ".join(f"{v.value}{v.unit}({v.reason})" for v in gate.violations),
                )

        sources = [_source_from_chunk(i, c) for i, c in enumerate(chunks, 1)]
        yield _sse("sources", SseSourcesEvent(sources=sources))
        for block in turn.block_list:
            yield _sse_raw("infographic", block.as_event())
        if turn.suggestions:
            yield _sse("suggestions", SseSuggestionsEvent(items=turn.suggestions))

        elapsed = _elapsed(p)
        with tx() as cur:
            repo.finish_message(
                cur, assistant_id, "".join(pieces).strip(), "COMPLETE", elapsed, finish_reason
            )
            # 답을 만든 판정만 다음에 다시 쓴다. 근거가 없어 막히거나 값이 없던 판정은
            # 틀렸을 수 있다(ARC-014).
            if finish_reason in _ANSWERED:
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
        message = exc.message
        if exc.code == "AI_UNAVAILABLE":
            # 연결 오류 원문은 운영 기록에만 둔다. 화면에는 쓸 수 없다는 것과 대신 볼 곳을 말한다
            log.warning(
                "질의 중 모델 서버 장애 conversation=%s: %s", p.conversation_id, exc.message
            )
            message = MODEL_UNAVAILABLE
        yield _sse_raw("error", {"code": exc.code, "message": message})
    except Exception:
        log.exception("질의 처리 실패 conversation=%s", p.conversation_id)
        _abort(assistant_id, pieces, p)
        yield _sse_raw("error", {"code": "INTERNAL", "message": "답변 생성 중 오류가 났습니다."})


# 모델·임베딩 서버에 닿지 못했을 때의 안내(AC-060-9). 값은 현황 화면이 같은 집계로 보여 준다
MODEL_UNAVAILABLE = (
    "AI 모델 서버를 지금 쓸 수 없어 답변을 만들지 못했습니다. "
    "진척·이슈 수치는 현황 화면에서 확인할 수 있습니다. 잠시 뒤 다시 질문해 주세요."
)

# 답의 종류(done.finishReason). 모델이 쓴 답은 STOP·PARTIAL·NUMBER_GUARD, 나머지는 서버 문안이다.
STOP = "STOP"
PARTIAL = "PARTIAL"
NUMBER_GUARD = "NUMBER_GUARD"
CLARIFY = "CLARIFY"
OFF_TOPIC = "OFF_TOPIC"
NO_DOCUMENTS = "NO_DOCUMENTS"
NO_RELEVANT_DOCUMENTS = "NO_RELEVANT_DOCUMENTS"
NO_DATA = "NO_DATA"
UNSUPPORTED = "UNSUPPORTED"
QUERY_ERROR = "QUERY_ERROR"
# 검색 모델과 색인이 달라 문서 검색을 멈춘 상태(ARC-022). 조회 오류와 다르게 알린다
SEARCH_DISABLED = "SEARCH_DISABLED"
# 모델 장애로 집계 값만 서버 문안으로 낸 답(AC-060-9). 판정은 다시 캐시에 남기지 않는다
MODEL_DOWN = "MODEL_DOWN"
_ANSWERED = (STOP, PARTIAL, NUMBER_GUARD)


def _model_down_answer(turn: "_Turn") -> str | None:
    """모델 없이 낼 수 있는 집계 값 답. 집계·일정 값이 없으면 None(쓸 수 없음 안내로 간다)."""
    if turn.aggregate is not None and turn.aggregate.lines:
        return answer.model_down_values(turn.aggregate.title, turn.aggregate.lines)
    intent = turn.intent
    if intent is not None and intent.lines:
        return answer.model_down_values(intent.title, intent.lines)
    return None


class _QueryFailed(Exception):
    """조회가 깨졌다. 값이 없는 것과 다르다. 사용자에게 데이터 없음으로 말하지 않는다."""


@dataclass
class _Turn:
    """한 질문의 재료와 답의 종류. reason 이 서면 모델을 부르지 않고 text 를 내보낸다."""

    decision: routing.RouteDecision
    aggregate: answer.AggregateContext | None = None
    block_list: list[blocks.Block] = field(default_factory=list)
    table: entity_table.EntityTable | None = None
    intent: intents.IntentResult | None = None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    gate_ok: bool = False
    found_count: int = 0
    max_similarity: float = 0.0
    reason: str | None = None
    text: str | None = None
    notice: str | None = None  # 모델 답 뒤에 붙는 서버 문안. 있으면 부분 답이다
    footnote: str | None = None  # 모델 답 뒤에 붙는 서버 설명(계획선이 추정이라는 것 등)
    suggestions: list[SuggestionItem] = field(default_factory=list)

    def stop(self, reason: str, text: str) -> None:
        self.reason, self.text = reason, text


def _resolve(
    cur: Any,
    p: Prepared,
    turn: _Turn,
    query_vec: list[float] | None,
    query_text: str,
) -> None:
    """판정대로 값을 뽑고 답의 종류를 정한다. 값은 전부 시맨틱 레이어·WBS·스냅샷에서 온다."""
    _server_table(cur, p, turn)
    decision = turn.decision
    related = list(decision.related)

    if decision.type == routing.CLARIFY:
        options = suggest.build(cur, p.principal, p.scope, p.catalog, decision.options, set())
        if options:
            turn.suggestions = options
            turn.stop(CLARIFY, answer.clarify())
            return
        # 고를 것이 남지 않았으면 되묻지 않는다. 문서에서 찾아본다
        decision = turn.decision = routing.RouteDecision(
            type=routing.DOCUMENT, rewritten=decision.rewritten
        )

    if decision.type == routing.INTENT:
        assert decision.intent is not None
        related = list(suggest.FOLLOWS.get(decision.intent, ())) + related
        try:
            with cur.connection.transaction():
                result = intents.run(cur, decision.intent, decision.period, p.scope)
        except Exception:  # noqa: BLE001 — 조회 오류는 값 없음과 다르게 알린다
            log.exception("일정 질문 조회 실패 intent=%s", decision.intent)
            turn.stop(QUERY_ERROR, answer.query_error())
        else:
            if result.server_text:
                # 모델이 쓸 것이 없다. 있는 값과 없는 이유를 서버가 그대로 말한다
                reason = PARTIAL if result.status == intents.PARTIAL else NO_DATA
                turn.stop(reason, result.server_text)
            elif result.status == intents.NO_DATA and decision.intent != intents.DELAY_CAUSE:
                turn.stop(NO_DATA, result.notice or answer.unsupported())
            elif result.status != intents.NO_DATA:
                turn.intent = result
                made = result.block(len(turn.block_list) + 1)
                if made is not None:
                    turn.block_list.append(made)
                if result.status == intents.PARTIAL:
                    turn.notice = result.notice
                turn.footnote = result.footnote

    if decision.type == routing.AGGREGATE:
        assert decision.measure is not None
        try:
            aggregate, infographic = _aggregate(cur, p, decision)
        except _QueryFailed:
            turn.stop(QUERY_ERROR, answer.query_error())
        else:
            if aggregate is None:
                turn.stop(UNSUPPORTED, answer.unsupported())
            elif not overview.has_value(aggregate.data):
                # 값이 없는 지표를 문서 경로로 돌리지 않는다. 무엇이 없는지 말한다.
                # 수집한 건수가 비었으면 0건이거나 셀 자료가 없는 것이다. 둘을 가른다(GH-127)
                counted, reason_text = _empty_count(cur, p, decision)
                if counted is not None:
                    turn.aggregate = counted
                else:
                    turn.stop(
                        NO_DATA,
                        reason_text
                        or answer.no_measure_data(decision.measure.label, aggregate.data.basis),
                    )
            else:
                turn.aggregate = aggregate
                # 나눠 보기를 묻지 않은 질문("일반 이슈가 몇 건이야")에는 그림을 붙이지 않는다
                # (UC-060-S02 「그림 없음」). 기본 차원으로 나눈 값은 프롬프트에만 들어간다
                drawn = (
                    infographic is not None
                    and decision.breakdown
                    and blocks.worth_drawing(infographic.data)
                )
                if not drawn and aggregate.data.basis:
                    # 그림이 없으면 화면에 산출 근거가 보일 곳이 없다. 모델이 근거 문구를 줄여
                    # 옮기기도 한다(「발주기관이 지정」이 빠짐, DEF-V061). 서버 문안으로 붙인다
                    turn.footnote = f"산출 근거: {aggregate.data.basis}"
                if drawn:
                    # 값이 하나뿐이면 문장이 그 숫자를 말한다. 그림은 붙이지 않는다. 값은
                    # aggregate 로 프롬프트와 수치 검문에 그대로 들어간다(ARC-013 4-1).
                    turn.block_list.append(
                        blocks.from_aggregate(
                            len(turn.block_list) + 1,
                            infographic.template,
                            infographic.title,
                            infographic.data,
                            aggregate.lines,
                        )
                    )

    if turn.reason is None:
        found = _lookup(cur, p, turn)
        if not found:
            _listing_and_overview(cur, p, turn)
        if turn.reason is None:
            _search(cur, p, turn, query_vec, query_text)
            if found:
                # 적힌 ID 로 찾은 항목이 근거다. 유사도 검색 조각은 그 뒤에 붙인다
                ids = {c.id for c in found.chunks}
                rest = [c for c in turn.chunks if c.id not in ids]
                turn.chunks = (found.chunks + rest)[: max(len(found.chunks), settings.rag_top_k)]
                turn.gate_ok = True
        _decide_reason(turn)

    if turn.reason not in (CLARIFY, OFF_TOPIC):
        exclude = {routing.current_key(turn.decision)}
        turn.suggestions = suggest.build(cur, p.principal, p.scope, p.catalog, related, exclude)


def _server_table(cur: Any, p: Prepared, turn: _Turn) -> bool:
    """착수보고 대표 질의 중 모델 판정이 빗나가던 두 질문을 글자로 알아보고 서버가 표로 답한다.
    「이번 달 마일스톤 현황」은 준수율 지표로, 「지난 보고 이후 변경 사항」은 지금 값 요약으로
    갔다(11-23 실측). 목록 질문과 권장 질문을 누른 경우는 건드리지 않는다."""
    decision = turn.decision
    if decision.listing or p.target is not None:
        return False
    text = None
    if milestones.asks(p.question):
        block, text = milestones.build(cur, p.question, list(p.scope), 1)
    elif changes.asks(p.question):
        block = changes.build(cur, p.question, list(p.scope), 1)
        if block is None:
            return False
    else:
        return False
    turn.decision = routing.RouteDecision(
        type=routing.DOCUMENT, rewritten=decision.rewritten, related=decision.related
    )
    if block is None:
        turn.stop(NO_DATA, text or answer.unsupported())
    else:
        turn.block_list.append(block)
    return True


def _lookup(cur: Any, p: Prepared, turn: _Turn) -> lookup.Found:
    """질문에 적힌 이슈 번호·요구사항 코드를 글자 그대로 찾는다. 지표·일정 질문과 목록 질문은
    그 경로가 답한다. 문서·현황 질문으로 판정된 것만 여기서 받는다."""
    decision = turn.decision
    if decision.listing or decision.type not in (
        routing.DOCUMENT, routing.MIXED, routing.OVERVIEW, routing.OFF_TOPIC
    ):
        return lookup.Found()
    found = lookup.find(cur, p.question, list(p.scope), len(turn.block_list) + 1)
    if found:
        turn.block_list.extend(found.blocks)
        turn.decision = routing.RouteDecision(
            type=routing.DOCUMENT, rewritten=decision.rewritten, related=decision.related
        )
    return found


def _listing_and_overview(cur: Any, p: Prepared, turn: _Turn) -> None:
    decision = turn.decision
    # 목록은 표준 모델에서 행을 꺼내 표로 그린다. 청크에는 상태가 없어 조건을 못 건다
    # (ARC-013). 09.17 실측에서 닫힌 이슈가 "작업이 안 된" 목록에 섞였다.
    if decision.listing:
        entity = entity_table.FROM_SOURCE_TYPE.get(decision.listing)
        # 「최근 5일 이내 작업된 요구사항」처럼 기간을 물으면 그 기간에 활동한 것만 꺼낸다.
        # 기간은 질문 글자에서만 읽는다(모델이 고르지 않는다)
        period = None
        if entity and entity_table.supports_period(entity):
            period = question_period.activity_range(p.question)
        status = decision.listing_status
        if entity == "ISSUE" and "결함" in p.question:
            # 결함을 물었는데 일반 이슈 표를 주면 모델이 문서 속 숫자로 답한다(11-23 실측:
            # 결함이 없는 사업에서 취약점 문서의 「HIGH 7건」을 결함 7건이라 했다)
            entity = "DEFECT"
        if entity == "WORK_PRODUCT" and "미제출" in p.question:
            # 「미제출 산출물」은 처리 중(승인 전)과 다르다. 모델이 고르지 않고 글자에서 읽는다
            status = entity_table.MISSING
        if entity:
            turn.table = entity_table.build(
                cur, entity, status, p.scope, settings.rag_list_limit, period
            )
        if entity and period is not None and turn.table is None:
            # 기간 안에 활동이 없다. 청크 목록으로 돌리면 기간과 무관한 것이 나온다. 서버가 말한다
            label = entity_table.ENTITIES[entity].label
            last = entity_table.last_activity(cur, entity, p.scope)
            text = f"{period.label} 사이에 이슈가 생기거나 커밋·PR 이 붙은 {label} 항목이 없습니다."
            if last:
                text += f" 마지막 활동은 {last} 입니다."
            turn.stop(NO_DATA, text)
            return
        if entity == "DEFECT" and turn.table is None:
            # 이슈 조각으로 내려가면 결함이 아닌 이슈로 답한다. 없다고 서버가 말한다
            word = {entity_table.OPEN: "처리 중인", entity_table.CLOSED: "완료된"}.get(status, "")
            turn.stop(NO_DATA, answer.no_defects(word))
            return
        if turn.table is not None:
            turn.block_list.append(blocks.from_entity(len(turn.block_list) + 1, turn.table))
    # 전체 현황을 묻는 질문은 현황 그림으로 답한다(ARC-015). 다른 질문에는 붙이지 않는다
    if decision.type == routing.OVERVIEW:
        turn.block_list.extend(overview.build(cur, p.principal, p.scope, len(turn.block_list) + 1))


def _search(
    cur: Any, p: Prepared, turn: _Turn, query_vec: list[float] | None, query_text: str
) -> None:
    """근거를 어디서 찾을지. 표를 만들었으면 같은 목록을 청크로 또 넣지 않는다. 09.17
    실측에서 요구사항 41건이 표와 청크 양쪽으로 들어가 프롬프트가 불어나 모델이 시간 초과로
    끊겼다. 표가 답이고, 청크는 주제가 닿는 것만 출처로 붙인다."""
    decision = turn.decision
    if decision.type == routing.INTENT and decision.intent != intents.DELAY_CAUSE:
        return
    if query_vec is None:
        query_vec = embedding_port().embed([p.question])[0]
    try:
        with cur.connection.transaction():
            if decision.listing and turn.table is None:
                found = search.list_by_source(
                    cur,
                    decision.listing,
                    p.scope,
                    settings.rag_list_limit,
                    settings.rag_list_chars,
                )
            else:
                found = search.search_with_vector(cur, query_vec, query_text, p.scope)
    except errors.ApiError as exc:
        if exc.code != embedding_guard.MISMATCH:
            raise
        log.warning("문서 검색 멈춤 conversation=%s: %s", p.conversation_id, exc.message)
        if not turn.block_list and turn.aggregate is None:
            turn.stop(SEARCH_DISABLED, answer.search_disabled())
        return
    except Exception:  # noqa: BLE001 — 조회 오류는 값 없음과 다르게 알린다
        log.exception("문서 검색 실패 conversation=%s", p.conversation_id)
        if not turn.block_list and turn.aggregate is None:
            turn.stop(QUERY_ERROR, answer.query_error())
        return
    turn.gate_ok = found.passes_gate()
    turn.chunks = (
        search.attach_status(cur, [answer.focus_rows(c, query_text) for c in found.chunks])
        if turn.gate_ok
        else []
    )
    turn.found_count = found.candidate_count
    turn.max_similarity = found.max_similarity
    # 무관하다고 했는데 문서 근거가 실제로 있으면 문서 질문이다. 모델이 "인수 조건이
    # 뭐야" 를 무관으로 본 사례가 있어, 근거가 판정을 이긴다(ARC-015 3-3).
    if decision.type == routing.OFF_TOPIC and turn.gate_ok:
        turn.decision = routing.RouteDecision(type=routing.DOCUMENT, rewritten=decision.rewritten)


def _decide_reason(turn: _Turn) -> None:
    """모델을 부를지. 근거도 값도 없으면 이유를 갈라 서버 문안으로 끝낸다. 질문과 무관한
    고정 현황을 대신 붙이지 않는다(ARC-017 개정)."""
    if turn.reason is not None:
        return
    decision = turn.decision
    if turn.found_count == 0:
        no_docs, no_docs_text = NO_DOCUMENTS, answer.no_documents()
    else:
        no_docs = NO_RELEVANT_DOCUMENTS
        no_docs_text = answer.no_relevant_documents(turn.max_similarity)
    if decision.type == routing.OFF_TOPIC:
        # 사업과 무관한 질문. 현황으로 내려가면 날씨를 물었는데 진척률이 나온다
        turn.stop(OFF_TOPIC, answer.off_topic())
    elif decision.type == routing.DOCUMENT and not turn.gate_ok and not turn.block_list:
        # 근거 게이트(SWFR.RAG.007). 모델을 부르지 않는다.
        # 표가 만들어졌으면 근거가 있는 것이다. 표준 모델에서 꺼낸 행이라 색인이 비어
        # 있어도 답할 수 있다(ARC-013).
        if decision.listing:
            turn.stop(NO_DATA, answer.empty_listing(routing.LISTABLE[decision.listing]))
        else:
            turn.stop(no_docs, no_docs_text)
    elif decision.type == routing.OVERVIEW and not turn.block_list and not turn.gate_ok:
        turn.stop(NO_DATA, answer.no_overview_data())
    elif decision.type == routing.INTENT and decision.intent == intents.DELAY_CAUSE:
        if turn.gate_ok:
            return
        if turn.intent is None:
            turn.stop(no_docs, no_docs_text)
        else:
            # 늦은 작업까지는 확인했다. 사유는 근거가 없다고 서버가 말한다
            turn.notice = answer.no_delay_reason()


def _empty_count(
    cur: Any, p: Prepared, decision: routing.RouteDecision
) -> tuple[answer.AggregateContext | None, str | None]:
    """건수 지표가 비었을 때. 차원으로 묶으면 행이 없어도 전체는 0 이다(심각도별 막대가 빈
    목록이던 10-07 사례). 차원 없이 다시 세고, 수집이 끝난 사업만 0건으로 답한다. 수집 상태를
    믿을 수 없으면 0 을 말하지 않고 이유를 돌려준다. 수집 표가 아니면 둘 다 None."""
    measure = decision.measure
    assert measure is not None
    if measure.value_type != "COUNT" or measure.base_table not in collection.COLLECTED_TABLES:
        return None, None
    state = collection.status(cur, list(p.scope))
    if state != collection.COLLECTED:
        return None, answer.no_collected_data(measure.label, state)
    spec = WidgetSpec(
        template="STAT_CARD",
        title=decision.title,
        query=WidgetQuery(
            measure=measure.key, dimensions=[], filters=[], projectScope=list(p.scope)
        ),
        options=WidgetOptions(sort="desc"),
    )
    try:
        with cur.connection.transaction():
            data = semantic.run(cur, p.principal, spec)
    except Exception as exc:
        log.exception("건수 다시 세기 실패 measure=%s", measure.key)
        raise _QueryFailed from exc
    if not overview.has_value(data):
        return None, None
    return answer.AggregateContext.of(decision.title, data), None


def _aggregate(
    cur: Any, p: Prepared, decision: routing.RouteDecision
) -> tuple[answer.AggregateContext | None, InfographicEvent | None]:
    """모델이 고른 지표·차원·템플릿으로 시맨틱 레이어를 돌린다. 카탈로그 검증에서 막히면
    차원을 빼고 한 번 더 본다. 그래도 막히면 집계를 포기한다. 값을 억지로 만들지 않는다.
    조회 자체가 깨지면 _QueryFailed 다. 그것을 값 없음으로 말하지 않는다."""
    assert decision.measure is not None and decision.template is not None
    # 질문에 적힌 기간("이번 달")은 글자에서 읽어 필터로 건다. 모델에게 고르게 하지 않는다
    period = question_period.filter_for(p.question, decision.measure)
    attempts = [(decision.template, list(decision.dimensions))]
    if decision.dimensions:
        attempts.append(("STAT_CARD", []))
    for template, dimensions in attempts:
        spec = WidgetSpec(
            template=template,
            title=decision.title,
            query=WidgetQuery(
                measure=decision.measure.key,
                dimensions=dimensions,
                filters=[period] if period else [],
                projectScope=list(p.scope),
            ),
            options=WidgetOptions(sort="desc"),
        )
        try:
            with cur.connection.transaction():
                data = semantic.run(cur, p.principal, spec)
        except errors.ApiError as exc:
            if exc.code == "CATALOG_VALIDATION_FAILED":
                continue
            raise
        except Exception as exc:
            log.exception("집계 조회 실패 measure=%s", decision.measure.key)
            raise _QueryFailed from exc
        infographic = InfographicEvent(template=template, title=decision.title, data=data)
        return answer.AggregateContext.of(decision.title, data), infographic
    return None, None


def _route_type(turn: _Turn) -> str:
    decided = turn.decision.type
    if decided in (routing.INTENT, routing.CLARIFY):
        return decided
    if decided == routing.AGGREGATE:
        return routing.MIXED if turn.gate_ok else routing.AGGREGATE
    if decided == routing.OVERVIEW and turn.block_list:
        return routing.OVERVIEW
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
        finishReason=row.get("finish_reason"),
        suggestions=[SuggestionItem.model_validate(x) for x in row.get("suggestions_json") or []],
    )


def _facts(
    aggregate: answer.AggregateContext | None,
    block_list: list[blocks.Block],
    chunks: list[RetrievedChunk],
    scope_line: str | None,
    intent: intents.IntentResult | None = None,
) -> list[number_guard.Fact]:
    """수치 검문이 근거로 인정하는 값. 질문과 앞 답의 숫자는 넣지 않는다(ARC-017)."""
    facts: list[number_guard.Fact] = []
    if intent is not None:
        # 일정 값은 줄마다 기준일이 다를 수 있다(지난 스냅샷과 비교). 기준일을 모두 시점으로 둔다
        lines = [*intent.lines, *([intent.note] if intent.note else [])]
        facts += number_guard.facts_from_lines(
            lines,
            "일정",
            subject=intent.title,
            as_of=frozenset((d.year, d.month, d.day) for d in intent.dates),
        )
    if aggregate is not None:
        facts += number_guard.facts_from_lines(
            aggregate.lines,
            "집계",
            subject=f"{aggregate.title} {aggregate.data.measureLabel}",
            as_of=number_guard.as_of_date(aggregate.data.generatedAt),
        )
    for block in block_list:
        if intent is not None and block.data is intent.table:
            continue  # 위에서 기준일과 함께 넣었다
        lines = [*block.lines, *([block.note] if block.note else [])]
        data = block.data
        facts += number_guard.facts_from_lines(
            lines,
            f"그림 {block.slot}",
            subject=f"{block.title} {getattr(data, 'measureLabel', '')}",
            as_of=number_guard.as_of_date(getattr(data, "generatedAt", None)),
        )
    for no, chunk in enumerate(chunks, 1):
        facts += number_guard.facts_from_chunk(no, chunk.content)
    if scope_line:
        facts += number_guard.facts_from_lines([scope_line], "목록 범위")
    return facts


def _subjects(
    aggregate: answer.AggregateContext | None,
    block_list: list[blocks.Block],
    intent: intents.IntentResult | None = None,
) -> frozenset[str]:
    """수치의 대상어 사전. 기본 사전에 이번 답의 집계·그림 제목과 지표명을 더한다."""
    names = [intent.title] if intent is not None else []
    if aggregate is not None:
        names += [aggregate.title, aggregate.data.measureLabel]
    for block in block_list:
        names += [block.title, getattr(block.data, "measureLabel", "")]
    return number_guard.DOMAIN_TERMS | number_guard.keywords(" ".join(names))


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
        "location": answer.location_text(chunk),
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
        documentUrl=_document_url(chunk.source_type, chunk.project_id, chunk.source_id),
        pageNo=chunk.page_no,
        location=answer.location_text(chunk),
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
        documentUrl=_document_url(row["source_type"], project_id, row["source_id"]),
        pageNo=row["page_no"],
        # V59 전에 남긴 출처는 위치 문장이 없다. 쪽만이라도 보인다
        location=row.get("location") or (f"p.{row['page_no']}" if row["page_no"] else None),
    )


def _document_url(source_type: str, project_id: str, document_id: str | None) -> str | None:
    """업로드 문서는 외부 링크가 없다. 그 문서의 화면으로 보낸다(SWFR.RAG.006).

    청크가 재색인으로 사라져 문서를 모르면 문서 목록으로 보낸다.
    """
    if source_type != "DOCUMENT_UPLOAD" or not project_id:
        return None
    if document_id:
        return f"/p/{project_id}/documents/{document_id}"
    return f"/p/{project_id}/documents"


def _is_url(value: str | None) -> bool:
    return bool(value) and value.startswith(("http://", "https://"))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _sse(event: str, payload: BaseModel) -> bytes:
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n".encode()


def _sse_raw(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
