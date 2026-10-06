"""목록 질문에 표로 답하기 위한 표준 모델 조회 (ARC-013).

"아직 작업이 안 된 이슈 목록" 같은 질문은 청크 근거로는 못 답한다. 청크에는 제목과 본문만
있고 상태가 없어서, 모델이 열린 것과 닫힌 것을 가릴 수가 없다. 09.17 실측에서 닫힌 이슈
3건이 "작업이 안 된" 목록에 섞였고 근거 게이트도 수치 검문도 그것을 못 잡았다.

그래서 목록은 이슈 화면이 읽는 것과 같은 표준 모델 테이블에서 행을 꺼내 표로 만든다.
값도 필터도 SQL 이 정하므로 절대 규칙 1을 지키면서 질문의 조건에 정확히 답한다. 메뉴로
들어간 화면과 자연어 질의가 같은 데이터를 보는 것도 이 경로에서 성립한다.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db import fetch_all, fetch_one
from app.semantic.models import WidgetColumn, WidgetDataResponse, WidgetRow

# 상태 필터. 모델은 이 셋 중 하나만 고른다.
OPEN = "OPEN"
CLOSED = "CLOSED"
ALL = "ALL"
STATUSES = (OPEN, CLOSED, ALL)


@dataclass(frozen=True)
class EntitySpec:
    """어느 테이블에서 무엇을 꺼내 어떤 열로 보일지. 열 순서가 곧 표의 열 순서다."""

    key: str
    label: str  # 발주기관 어휘
    table: str
    columns: tuple[tuple[str, str, str], ...]  # (열 키, 열 이름, select 식)
    order_by: str
    # 열린 것과 닫힌 것을 가르는 SQL 조각. 상태가 없는 종류는 None
    open_clause: str | None
    closed_clause: str | None
    url_expr: str | None
    # 무엇을 뺀 범위인지. 표 설명과 범위 줄에 붙는다
    scope_note: str | None = None


ENTITIES: dict[str, EntitySpec] = {
    "ISSUE": EntitySpec(
        key="ISSUE",
        label="일반 이슈",
        table="issue e",
        columns=(
            ("title", "제목", "e.title"),
            ("status", "상태", "e.status"),
            ("severity", "심각도", "coalesce(e.severity, '-')"),
            ("assignee", "담당", "coalesce(e.assignee, '-')"),
            (
                "updated",
                "갱신일",
                "to_char(coalesce(e.source_updated_at, e.updated_at), 'YYYY-MM-DD')",
            ),
        ),
        # 급한 것이 위로. 심각도 순, 같으면 최근에 움직인 것. "가장 급한 작업" 이 이 순서를 읽는다
        order_by=(
            "case e.severity when 'BLOCKER' then 0 when 'CRITICAL' then 1 when 'MAJOR' then 2 "
            "when 'MINOR' then 3 when 'TRIVIAL' then 4 else 5 end, "
            "coalesce(e.source_updated_at, e.updated_at) desc nulls last"
        ),
        open_clause="e.status not in ('RESOLVED', 'CLOSED')",
        closed_clause="e.status in ('RESOLVED', 'CLOSED')",
        url_expr="e.external_url",
        scope_note="요구사항으로 분류된 항목 제외",
    ),
    "REQUIREMENT": EntitySpec(
        key="REQUIREMENT",
        label="요구사항",
        table="requirement e",
        columns=(
            ("code", "코드", "coalesce(e.code, '-')"),
            ("title", "제목", "e.title"),
            ("priority", "중요도", "coalesce(e.priority, '-')"),
            (
                "status",
                "상태",
                "case when e.status = 'IMPLEMENTED' and exists ("
                "select 1 from tool_connection c where c.id = e.tool_connection_id "
                "and c.tool = 'GITHUB') "
                "then '원천 이슈 닫힘(구현·검증 완료를 뜻하지 않음)' else e.status end",
            ),
        ),
        order_by="e.code nulls last, e.created_at",
        open_clause="e.status not in ('VERIFIED', 'ACCEPTED')",
        closed_clause="e.status in ('VERIFIED', 'ACCEPTED')",
        url_expr="e.external_url",
    ),
    "RISK": EntitySpec(
        key="RISK",
        label="리스크",
        table="risk e",
        columns=(
            ("title", "제목", "e.title"),
            ("status", "상태", "e.status"),
            ("severity", "심각도", "coalesce(e.severity, '-')"),
            ("owner", "담당", "coalesce(e.owner, '-')"),
        ),
        order_by="e.identified_at desc nulls last, e.created_at desc",
        open_clause="e.status <> 'CLOSED'",
        closed_clause="e.status = 'CLOSED'",
        url_expr="e.external_url",
    ),
    "WORK_PRODUCT": EntitySpec(
        key="WORK_PRODUCT",
        label="산출물",
        table="work_product e",
        columns=(
            ("type", "유형", "e.type"),
            ("title", "제목", "coalesce(e.title, '-')"),
            ("status", "상태", "e.status"),
            ("version", "버전", "coalesce(e.version, '-')"),
        ),
        order_by="e.type",
        open_clause="e.status <> 'APPROVED'",
        closed_clause="e.status = 'APPROVED'",
        url_expr="e.external_url",
    ),
}

# 문서 청크의 source_type 과 표준 모델 종류를 잇는다. 라우터는 청크 종류로 말한다.
FROM_SOURCE_TYPE = {
    "ISSUE": "ISSUE",
    "REQUIREMENT": "REQUIREMENT",
    "RISK": "RISK",
    "DOCUMENT_UPLOAD": "WORK_PRODUCT",
}

_STATUS_WORD = {OPEN: "처리 중", CLOSED: "완료", ALL: "전체"}


@dataclass
class EntityTable:
    """표 하나. data 는 위젯 렌더러가 그대로 읽고, lines 는 프롬프트와 수치 검문이 쓴다."""

    spec: EntitySpec
    status: str
    total: int
    data: WidgetDataResponse
    lines: list[str]

    @property
    def title(self) -> str:
        word = _STATUS_WORD[self.status]
        return f"{self.spec.label} 목록" if self.status == ALL else f"{word} {self.spec.label}"

    @property
    def scope_line(self) -> str:
        """본문이 건수를 말할 수 있게 범위를 한 줄로. 이 줄의 숫자는 검문의 근거가 된다."""
        shown = len(self.data.rows)
        note = f" ({self.spec.scope_note})" if self.spec.scope_note else ""
        if shown >= self.total:
            return f"{self.title} 전체 {self.total}건{note}"
        return f"{self.title} 총 {self.total}건 중 앞 {shown}건{note}"


def _where(spec: EntitySpec, status: str) -> str:
    if status == OPEN and spec.open_clause:
        return f" and {spec.open_clause}"
    if status == CLOSED and spec.closed_clause:
        return f" and {spec.closed_clause}"
    return ""


def build(
    cur: Any, entity: str, status: str, project_ids: list[str], limit: int
) -> EntityTable | None:
    """표준 모델에서 행을 꺼내 DATA_TABLE 모양으로 만든다. 범위가 비면 None."""
    spec = ENTITIES.get(entity)
    if spec is None or not project_ids:
        return None
    status = status if status in STATUSES else ALL
    clause = _where(spec, status)

    total_row = fetch_one(
        cur,
        f"select count(*) as n from {spec.table} where e.project_id = any(%s::uuid[]) {clause}",
        (project_ids,),
    )
    total = int(total_row["n"]) if total_row else 0
    if total == 0:
        return None

    selects = ", ".join(f"{expr} as {key}" for key, _, expr in spec.columns)
    url = f", {spec.url_expr} as external_url" if spec.url_expr else ""
    rows = fetch_all(
        cur,
        f"""
        select {selects}{url} from {spec.table}
         where e.project_id = any(%s::uuid[]) {clause}
         order by {spec.order_by}
         limit %s
        """,
        (project_ids, limit),
    )

    columns = [WidgetColumn(key=key, label=label, type="string") for key, label, _ in spec.columns]
    data = WidgetDataResponse(
        measure=f"entity_{spec.key.lower()}",
        measureLabel=f"{spec.label} ({spec.scope_note})" if spec.scope_note else spec.label,
        unit=None,
        dimensions=[],
        columns=columns,
        rows=[WidgetRow(values={k: r.get(k) for k, _, _ in spec.columns}) for r in rows],
        total=None,
        previousTotal=None,
        target=None,
        appliedProjectIds=list(project_ids),
        truncated=total > len(rows),
        generatedAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    lines = [
        "- " + " · ".join(f"{label} {r.get(key)}" for key, label, _ in spec.columns) for r in rows
    ]
    return EntityTable(spec=spec, status=status, total=total, data=data, lines=lines)
