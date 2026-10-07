"""권장 질문 (SWFR.RAG.005). 답 뒤에 이어 물을 것을 최대 셋 낸다.

모델은 키만 고른다(routing.parse_key). 문장은 서버 틀이고, 카탈로그·권한·실제 값이 있는지
확인한 것만 남긴다. 눌렀을 때 같은 '없음' 안내로 끝날 것은 내지 않는다. 남는 게 없으면 내지
않는다. 셋을 채우려고 관계없는 것을 넣지 않는다.
"""

import logging
from typing import Any

from app.auth.models import AuthPrincipal
from app.common import errors, korean
from app.rag import entity_table, intents, overview, routing
from app.rag.models import SuggestionItem
from app.semantic import service as semantic
from app.semantic.catalog import Catalog, MeasureDef
from app.semantic.models import WidgetOptions, WidgetQuery, WidgetSpec

log = logging.getLogger(__name__)

MAX = 3

_INTENT_QUESTIONS = {
    "intent:PLAN_VS_ACTUAL": "오늘 기준 계획 대비 진척은 어떤가요?",
    "intent:BEHIND_TASKS": "계획보다 늦은 작업은 무엇인가요?",
    "intent:PROGRESS_CHANGE:WEEK": "지난주보다 진척이 얼마나 바뀌었나요?",
    "intent:PROGRESS_CHANGE:MONTH": "지난달보다 진척이 얼마나 바뀌었나요?",
    "intent:DELAY_CAUSE": "늦어진 작업의 지연 사유는 무엇인가요?",
    routing.OVERVIEW_KEY: "사업 전체 현황을 요약해 주세요.",
}
_STATUS_WORD = {
    entity_table.OPEN: "처리 중인 ",
    entity_table.CLOSED: "완료된 ",
    entity_table.ALL: "",
}

# 일정 질문 뒤에 이어 볼 것. 질문 묶음끼리의 관계라 모델이 고른 것보다 앞에 둔다
FOLLOWS: dict[str, tuple[str, ...]] = {
    intents.PLAN_VS_ACTUAL: (
        "intent:BEHIND_TASKS",
        "intent:PROGRESS_CHANGE:WEEK",
        "intent:DELAY_CAUSE",
    ),
    intents.BEHIND_TASKS: ("intent:DELAY_CAUSE", "intent:PLAN_VS_ACTUAL"),
    intents.PROGRESS_CHANGE: ("intent:PLAN_VS_ACTUAL", "intent:BEHIND_TASKS"),
    intents.DELAY_CAUSE: ("intent:BEHIND_TASKS", "intent:PLAN_VS_ACTUAL"),
}


def question_for(target: routing.Target) -> str:
    if target.key in _INTENT_QUESTIONS:
        return _INTENT_QUESTIONS[target.key]
    if target.kind == routing.AGGREGATE and target.measure is not None:
        return measure_question(target.measure)
    if target.kind == routing.LIST and target.listing:
        label = routing.LISTABLE[target.listing]
        return f"{_STATUS_WORD[target.listing_status]}{label} 목록을 보여 주세요."
    return target.key


def measure_question(m: MeasureDef) -> str:
    """단위에 맞는 물음. 건수는 "몇 건", 비율은 "몇 퍼센트". 조사는 라벨 끝소리로 고른다."""
    subject = korean.attach(m.label, "은")
    if m.unit == "건":
        return f"{subject} 지금 몇 건인가요?"
    if m.unit == "%":
        return f"{subject} 현재 몇 퍼센트인가요?"
    return f"{subject} 현재 얼마인가요?"


def build(
    cur: Any,
    principal: AuthPrincipal,
    scope: list[str],
    catalog: Catalog,
    keys: list[str],
    exclude: set[str | None],
    limit: int = MAX,
) -> list[SuggestionItem]:
    """키를 검증하고 값이 있는 것만 문장으로. 순서를 지키고 겹치지 않게."""
    out: list[SuggestionItem] = []
    seen: set[str] = set()
    for raw in keys:
        if len(out) >= limit:
            break
        target = routing.parse_key(catalog, raw)
        if target is None or target.key in seen or target.key in exclude:
            continue
        seen.add(target.key)
        if not _available(cur, principal, scope, target):
            continue
        out.append(SuggestionItem(question=question_for(target), hint=target.key))
    return out


def _available(
    cur: Any, principal: AuthPrincipal, scope: list[str], target: routing.Target
) -> bool:
    """눌렀을 때 값이 나오는가. 확인하다 오류가 나면 내지 않는다(오류를 '없음'으로 보이지 않게
    권장하지 않을 뿐이다). 확인 쿼리는 세이브포인트 안에서 돌려 바깥 트랜잭션을 지킨다."""
    if not scope:
        return False
    try:
        with cur.connection.transaction():
            if target.kind == routing.INTENT:
                assert target.intent is not None
                return intents.available(cur, target.intent, scope)
            if target.kind == routing.OVERVIEW:
                return bool(overview.build(cur, principal, scope, 1))
            if target.kind == routing.LIST:
                entity = entity_table.FROM_SOURCE_TYPE.get(target.listing or "")
                return bool(entity) and (
                    entity_table.build(cur, entity, target.listing_status, scope, 1) is not None
                )
            if target.kind == routing.AGGREGATE and target.measure is not None:
                spec = WidgetSpec(
                    template="STAT_CARD",
                    title=target.measure.label,
                    query=WidgetQuery(
                        measure=target.measure.key,
                        dimensions=[],
                        filters=[],
                        projectScope=list(scope),
                    ),
                    options=WidgetOptions(),
                )
                return overview.has_value(semantic.run(cur, principal, spec))
    except errors.ApiError:
        return False
    except Exception:  # noqa: BLE001 — 권장 확인이 답을 막아선 안 된다
        log.exception("권장 질문 확인 실패 key=%s", target.key)
        return False
    return False
