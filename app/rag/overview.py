"""사업 현황 블록 (ARC-015). 문서를 가리키지 않는 일반 질문의 답이다.

"잘 되고 있어?", "문제 있어?", "뭐부터 봐야 해?" 는 문서에 적힌 사실이 아니라 표준 모델의
지금 상태를 묻는 것이다. 진척률·심각도별 열린 일반 이슈·지연 작업·미제출 산출물·열린 리스크를
시맨틱 레이어로 뽑아 그림 몇 장으로 넘기고, 모델은 그 값만으로 요약을 쓴다(절대 규칙 1).

근거 게이트에 막힌 문서 질문도 여기로 내려온다. "맞는 문서는 못 찾았지만 지금 상태는 이렇다"
가 "답을 만들지 않았다" 보다 낫다. 데이터가 아예 없는 사업에서만 예전처럼 막는다.
"""

from dataclasses import dataclass
from typing import Any

from app.auth.models import AuthPrincipal
from app.common import errors
from app.rag import answer, blocks
from app.semantic import service as semantic
from app.semantic.models import WidgetOptions, WidgetQuery, WidgetSpec


@dataclass(frozen=True)
class OverviewSpec:
    measure: str
    dimensions: tuple[str, ...]
    template: str
    title: str


# 순서가 곧 그림 순서다. 카탈로그에 없는 지표는 건너뛴다. 값이 없는 그림은 안 넣는다.
SPECS: tuple[OverviewSpec, ...] = (
    OverviewSpec("progress_representative_pct", (), "STAT_CARD", "진척률"),
    OverviewSpec("open_issue_count", ("issue_severity",), "BAR_CHART", "심각도별 열린 일반 이슈"),
    OverviewSpec("progress_behind_task_count", (), "STAT_CARD", "지연 작업"),
    OverviewSpec("work_product_missing_count", (), "STAT_CARD", "미제출 산출물"),
    OverviewSpec("open_risk_count", (), "STAT_CARD", "열린 리스크"),
)
MAX_BLOCKS = 4

LEAD = "질문에 꼭 맞는 문서는 찾지 못했습니다. 지금 사업 현황으로 답합니다.\n\n"


def build(
    cur: Any, principal: AuthPrincipal, scope: list[str], first_slot: int = 1
) -> list[blocks.Block]:
    """현황 그림을 만든다. 하나도 못 만들면 빈 목록이다. 값을 억지로 만들지 않는다."""
    made: list[blocks.Block] = []
    for spec in SPECS:
        if len(made) >= MAX_BLOCKS:
            break
        widget = WidgetSpec(
            template=spec.template,
            title=spec.title,
            query=WidgetQuery(
                measure=spec.measure,
                dimensions=list(spec.dimensions),
                filters=[],
                projectScope=list(scope),
            ),
            options=WidgetOptions(sort="desc"),
        )
        try:
            data = semantic.run(cur, principal, widget)
        except errors.ApiError as exc:
            if exc.code in ("CATALOG_VALIDATION_FAILED", "VALIDATION_FAILED"):
                continue
            raise
        if not _has_value(data):
            continue
        made.append(
            blocks.from_aggregate(
                first_slot + len(made),
                spec.template,
                spec.title,
                data,
                answer.aggregate_lines(data),
            )
        )
    return made


def _has_value(data) -> bool:
    """값이 하나도 없는 그림은 안 넣는다. "진척률: 값 없음" 은 현황이 아니라 빈칸이다."""
    rows = [r for r in data.rows if r.values.get("value") is not None]
    if rows:
        return True
    return data.total is not None and data.total.values.get("value") is not None
