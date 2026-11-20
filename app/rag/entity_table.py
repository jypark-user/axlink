"""목록 질문에 표로 답하기 위한 표준 모델 조회 (ARC-013).

"아직 작업이 안 된 이슈 목록" 같은 질문은 청크 근거로는 못 답한다. 청크에는 제목과 본문만
있고 상태가 없어서, 모델이 열린 것과 닫힌 것을 가릴 수가 없다. 09.17 실측에서 닫힌 이슈
3건이 "작업이 안 된" 목록에 섞였고 근거 게이트도 수치 검문도 그것을 못 잡았다.

그래서 목록은 이슈 화면이 읽는 것과 같은 표준 모델 테이블에서 행을 꺼내 표로 만든다.
값도 필터도 SQL 이 정하므로 절대 규칙 1을 지키면서 질문의 조건에 정확히 답한다. 메뉴로
들어간 화면과 자연어 질의가 같은 데이터를 보는 것도 이 경로에서 성립한다.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db import fetch_all, fetch_one
from app.rag import vocab
from app.rag.question_period import ActivityRange
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
    # 정렬 기준. 범위 줄에만 붙인다(표 제목에는 넣지 않음). 모델이 순서를 등급으로 읽지 않게
    order_note: str | None = None
    # 활동 사건 (시각, 종류, 대상 id) 을 내는 SQL. 기간을 물은 목록만 쓴다. None 이면 기간을 못 건다
    activity_events: str | None = None


# 이행률 범위(DEC-11). app.standard.repository.in_rate_scope 와 같은 조건이다. 확정 전이면 전부 든다
_IN_SCOPE = (
    "(e.baseline_id is not null or not exists (select 1 from requirement_baseline rb "
    "where rb.project_id = e.project_id and rb.status = 'CONFIRMED'))"
)

# 활동 사건. 사용자 정의(11-20): 이슈가 생겼거나 그 이슈에 커밋·PR 이 붙었으면 작업한 것이다.
# 요구사항은 자기 이슈와 추적 연결로 이어진 이슈, 그리고 그 둘에 붙은 커밋·PR 을 본다.
# 요구사항 출처가 명세서면 생성 시각이 없다(source_created_at null). 연결된 활동만 센다
_SELF_CREATED = "select e.source_created_at, 'ISSUE', e.id"
_LINKED_ISSUES = (
    "select i.source_created_at, 'ISSUE', i.id from trace_link li"
    " join issue i on i.id = li.from_id"
    " where li.from_type = 'ISSUE' and li.to_type = 'REQUIREMENT'"
    " and li.status = 'ACTIVE' and li.to_id = e.id"
)
_CHANGES_ON_SELF = (
    "select c.occurred_at, 'CHANGE', c.id from trace_link t"
    " join code_change c on c.id = t.from_id"
    " where t.from_type = 'CODE_CHANGE' and t.status = 'ACTIVE' and t.to_id = e.id"
)
_CHANGES_ON_LINKED_ISSUES = (
    "select c.occurred_at, 'CHANGE', c.id from trace_link li"
    " join trace_link t on t.to_id = li.from_id and t.to_type = 'ISSUE'"
    " and t.from_type = 'CODE_CHANGE' and t.status = 'ACTIVE'"
    " join code_change c on c.id = t.from_id"
    " where li.from_type = 'ISSUE' and li.to_type = 'REQUIREMENT'"
    " and li.status = 'ACTIVE' and li.to_id = e.id"
)

ENTITIES: dict[str, EntitySpec] = {
    "ISSUE": EntitySpec(
        key="ISSUE",
        label="일반 이슈",
        table="issue e",
        columns=(
            ("title", "제목", "e.title"),
            ("status", "상태", "e.status"),
            ("severity", "심각도", "coalesce(e.severity, '미지정')"),
            ("assignee", "담당", "coalesce(e.assignee, '-')"),
            (
                "updated",
                "갱신일",
                "to_char(coalesce(e.source_updated_at, e.updated_at), 'YYYY-MM-DD')",
            ),
        ),
        # 급한 것이 위로. 심각도 순, 같으면 최근에 움직인 것. "가장 급한 작업" 이 이 순서를 읽는다
        order_by=(
            # 심각도가 지정된 것을 심각도 순으로 먼저 두고, 미지정은 별도 묶음으로 뒤에 둔다.
            # 미지정은 등급이 아니다. 중대·경미 사이에 끼우지 않는다(GH-116).
            # 묶음 안에서는 최근 갱신순
            "(e.severity is null), "
            "case e.severity when 'BLOCKER' then 0 when 'CRITICAL' then 1 when 'MAJOR' then 2 "
            "when 'MINOR' then 3 when 'TRIVIAL' then 4 end, "
            "coalesce(e.source_updated_at, e.updated_at) desc nulls last"
        ),
        open_clause="e.status not in ('RESOLVED', 'CLOSED')",
        closed_clause="e.status in ('RESOLVED', 'CLOSED')",
        url_expr="e.external_url",
        scope_note="예전에 요구사항으로 만든 이슈 제외",
        order_note=(
            "심각도가 지정된 이슈를 심각도 순으로 먼저 두고, 심각도 미지정은 별도 묶음으로 뒤에 "
            "최근 갱신순으로 둔다. 미지정은 위험 등급이 아니다"
        ),
        activity_events=f"{_SELF_CREATED} union all {_CHANGES_ON_SELF}",
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
                "case when e.decided_status is not null "
                "then e.status || '(발주기관 지정)' "
                "when e.status = 'IMPLEMENTED' and exists ("
                "select 1 from tool_connection c where c.id = e.tool_connection_id "
                "and c.tool = 'GITHUB') "
                "then '출처 이슈 닫힘(구현 확인 아님)' else e.status end",
            ),
            # 확정 명세서에 없는 기존 요구사항은 지우지 않고 구분해 보인다(DEC-11 (a)).
            # 이행률 분모에도 들지 않는다
            ("scope", "범위", f"case when {_IN_SCOPE} then '확정 목록' "
                             "else '확정 명세서에 없음(이행률 제외)' end"),
        ),
        order_by=f"({_IN_SCOPE}) desc, e.code nulls last, e.created_at",
        activity_events=" union all ".join(
            (_SELF_CREATED, _LINKED_ISSUES, _CHANGES_ON_SELF, _CHANGES_ON_LINKED_ISSUES)
        ),
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
    period: ActivityRange | None = None

    @property
    def title(self) -> str:
        word = _STATUS_WORD[self.status]
        name = f"{self.spec.label} 목록" if self.status == ALL else f"{word} {self.spec.label}"
        if self.period is not None:
            return f"{self.period.label} 활동이 있는 {name}"
        return name

    @property
    def scope_line(self) -> str:
        """본문이 건수를 말할 수 있게 범위를 한 줄로. 이 줄의 숫자는 검문의 근거가 된다."""
        shown = len(self.data.rows)
        note = f" ({self.spec.scope_note})" if self.spec.scope_note else ""
        if self.period is not None:
            note += f". {ACTIVITY_NOTE}. 정렬: 최근 활동순"
        elif self.spec.order_note:
            note += f". 정렬: {self.spec.order_note}"
        if shown >= self.total:
            return f"{self.title} 전체 {self.total}건{note}"
        return f"{self.title} 총 {self.total}건 중 앞 {shown}건{note}"


ACTIVITY_NOTE = (
    "활동은 기간 안에 이슈가 생겼거나(요구사항은 추적 연결된 이슈 포함) 커밋·PR 이 붙은 것이다. "
    "추적 연결이 없는 커밋은 들지 않는다"
)

# 기간을 물은 목록에 붙는 열. 왜 들었는지를 표에 그대로 보인다
_ACTIVITY_COLUMNS = (
    ("last_activity", "최근 활동", "to_char(act.last_at at time zone 'Asia/Seoul', 'YYYY-MM-DD')"),
    (
        "activity",
        "활동",
        "concat_ws(' · ', case when act.issues > 0 then '이슈 ' || act.issues || '건' end, "
        "case when act.changes > 0 then '커밋·PR ' || act.changes || '건' end)",
    ),
)


def supports_period(entity: str) -> bool:
    spec = ENTITIES.get(entity)
    return spec is not None and spec.activity_events is not None


def _activity_join(spec: EntitySpec) -> str:
    """기간 안의 활동을 한 행으로 묶는 lateral. 기간 밖 사건만 있으면 그 행은 빠진다."""
    return f"""
        join lateral (
          select max(ev.at) as last_at,
                 count(distinct ev.ref) filter (where ev.kind = 'ISSUE') as issues,
                 count(distinct ev.ref) filter (where ev.kind = 'CHANGE') as changes
            from ({spec.activity_events}) as ev(at, kind, ref)
           where ev.at is not null
             and (ev.at at time zone 'Asia/Seoul')::date between %s and %s
        ) act on act.last_at is not null"""


def _where(spec: EntitySpec, status: str) -> str:
    if status == OPEN and spec.open_clause:
        return f" and {spec.open_clause}"
    if status == CLOSED and spec.closed_clause:
        return f" and {spec.closed_clause}"
    return ""


def build(
    cur: Any,
    entity: str,
    status: str,
    project_ids: list[str],
    limit: int,
    period: ActivityRange | None = None,
) -> EntityTable | None:
    """표준 모델에서 행을 꺼내 DATA_TABLE 모양으로 만든다. 범위가 비면 None.

    period 가 있으면 그 기간에 활동(이슈 생성, 커밋·PR 연결)이 있는 것만 최근 활동순으로 꺼내고,
    최근 활동 날짜와 활동 건수 열을 붙인다. 활동을 셀 수 없는 종류면 기간을 무시한다.
    """
    spec = ENTITIES.get(entity)
    if spec is None or not project_ids:
        return None
    status = status if status in STATUSES else ALL
    clause = _where(spec, status)
    if spec.activity_events is None:
        period = None
    join = _activity_join(spec) if period is not None else ""
    join_params: tuple[Any, ...] = (period.start, period.end) if period is not None else ()
    columns_def = spec.columns + (_ACTIVITY_COLUMNS if period is not None else ())
    order_by = "act.last_at desc, e.id" if period is not None else spec.order_by

    total_row = fetch_one(
        cur,
        f"select count(*) as n from {spec.table}{join}"
        f" where e.project_id = any(%s::uuid[]) {clause}",
        (*join_params, project_ids),
    )
    total = int(total_row["n"]) if total_row else 0
    if total == 0:
        return None

    selects = ", ".join(f"{expr} as {key}" for key, _, expr in columns_def)
    url = f", {spec.url_expr} as external_url" if spec.url_expr else ""
    rows = fetch_all(
        cur,
        f"""
        select {selects}{url} from {spec.table}{join}
         where e.project_id = any(%s::uuid[]) {clause}
         order by {order_by}
         limit %s
        """,
        (*join_params, project_ids, limit),
    )

    # 상태·심각도 코드는 화면과 같은 발주기관 어휘로 바꿔 표와 답 재료에 넣는다(UC-060-S16)
    rows = [{k: _word(k, v) for k, v in r.items()} for r in rows]
    columns = [WidgetColumn(key=key, label=label, type="string") for key, label, _ in columns_def]
    data = WidgetDataResponse(
        measure=f"entity_{spec.key.lower()}",
        measureLabel=f"{spec.label} ({spec.scope_note})" if spec.scope_note else spec.label,
        unit=None,
        dimensions=[],
        columns=columns,
        rows=[WidgetRow(values={k: r.get(k) for k, _, _ in columns_def}) for r in rows],
        total=None,
        previousTotal=None,
        target=None,
        appliedProjectIds=list(project_ids),
        truncated=total > len(rows),
        generatedAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    lines = [
        "- " + " · ".join(f"{label} {r.get(key)}" for key, label, _ in columns_def) for r in rows
    ]
    return EntityTable(
        spec=spec, status=status, total=total, data=data, lines=lines, period=period
    )


def last_activity(cur: Any, entity: str, project_ids: list[str]) -> str | None:
    """기간 안에 활동이 없을 때 알려 줄 마지막 활동 날짜(사업 시간대). 없으면 None."""
    spec = ENTITIES.get(entity)
    if spec is None or spec.activity_events is None or not project_ids:
        return None
    row = fetch_one(
        cur,
        f"""
        select to_char(max(ev.at) at time zone 'Asia/Seoul', 'YYYY-MM-DD') as last_day
          from {spec.table}
          join lateral ({spec.activity_events}) as ev(at, kind, ref) on true
         where e.project_id = any(%s::uuid[])
        """,
        (project_ids,),
    )
    return row["last_day"] if row else None


_CODE_HEAD = re.compile(r"^([A-Z_]+)(?=\()")


def _word(key: str, value: Any) -> Any:
    """상태·심각도 열의 코드만 바꾼다. "IMPLEMENTED(발주기관 지정)" 처럼 코드 뒤에 설명이 붙은
    값은 앞 코드만 바꾼다."""
    if key not in ("status", "severity") or not isinstance(value, str):
        return value
    head = _CODE_HEAD.match(value)
    if head:
        return str(vocab.word(head.group(1))) + value[head.end() :]
    return vocab.word(value)
