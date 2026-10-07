"""위젯 명세 검증과 SQL 조립.

두 단계로 나뉜다.

1. validate: 명세의 measure·dimension·filter 가 전부 카탈로그에 있고 허용된 짝인지 본다.
             하나라도 없으면 CATALOG_VALIDATION_FAILED. 조립까지 가지 않는다.
2. build:    검증된 정의의 SQL 조각(select_expr·join_clause·row_filter·value_expr·column_expr)을
             이어 붙인다. 사용자가 준 값(필터 값·사업 ID·limit)은 전부 바인드 파라미터다.

문자열이 SQL 에 들어가는 경로는 카탈로그 표 하나뿐이다. 그 표는 마이그레이션만 쓴다.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from app.common import errors
from app.dashboard.widget_template import DEFAULT_LIMIT, fits, is_template, row_cap
from app.semantic.catalog import Catalog, DimensionDef, FilterDef, MeasureDef, filter_key
from app.semantic.models import WidgetColumn, WidgetFilter, WidgetOptions, WidgetSpec

# 기간 축·기간 필터가 가리키는 시각 컬럼. 표마다 "언제의 일인가" 가 다른 컬럼에 있다.
TIME_COLUMNS: dict[str, str] = {
    "requirement": "e.source_created_at",
    "issue": "coalesce(e.source_created_at, e.created_at)",
    "work_product": "coalesce(e.submitted_at, e.created_at)",
    "risk": "coalesce(e.identified_at::timestamptz, e.created_at)",
    "code_change": "e.occurred_at",
    "change_request": "e.requested_at",
    "correction_action": "e.created_at",
    "progress_record": "e.period_end",
    "progress_snapshot": "e.snapshot_date",
    "wbs_item": "coalesce(e.end_on::timestamptz, e.updated_at)",
    # 완료 확인 뷰(V46). 확인된 작업은 확인 시각, 아니면 작업 종료일
    "v_wbs_completion": "coalesce(e.decided_at, e.end_on::timestamptz)",
}

_TIME_COL = "<TIME_COL>"
MAX_DIMENSIONS = 2
MAX_FILTERS = 5

_JOIN_START = re.compile(
    r"(?i)\b(?:(?:left|right|full)\s+(?:outer\s+)?|inner\s+|cross\s+)?join\b"
)


def catalog_error(message: str) -> errors.ApiError:
    return errors.ApiError(400, "CATALOG_VALIDATION_FAILED", message)


@dataclass(frozen=True)
class BoundFilter:
    definition: FilterDef
    values: list[Any]


@dataclass
class ValidatedSpec:
    template: str
    title: str
    measure: MeasureDef
    dimensions: list[DimensionDef]
    filters: list[BoundFilter]
    project_ids: list[str]
    options: WidgetOptions
    limit: int
    catalog: Catalog


@dataclass
class BuiltQuery:
    sql: str
    params: dict[str, Any] = field(default_factory=dict)
    columns: list[WidgetColumn] = field(default_factory=list)


# ---------------------------------------------------------------- validate


def validate(catalog: Catalog, spec: WidgetSpec, allowed_project_ids: list[str]) -> ValidatedSpec:
    if not is_template(spec.template):
        raise errors.validation_failed(f"알 수 없는 위젯 템플릿: {spec.template}")
    query = spec.query
    if not query.measure:
        raise errors.validation_failed("query.measure 가 필요합니다.")

    measure = catalog.measure(query.measure)
    if measure is None:
        raise catalog_error(f"알 수 없는 measure: {query.measure}")

    dimensions: list[DimensionDef] = []
    for key in query.dimensions:
        if key not in measure.allowed_dimensions:
            raise catalog_error(f"measure 가 허용하지 않는 dimension: {key}")
        definition = catalog.dimension(key)
        if definition is None:
            raise catalog_error(f"알 수 없는 dimension: {key}")
        if definition in dimensions:
            raise catalog_error(f"dimension 이 중복됩니다: {key}")
        dimensions.append(definition)
    if len(dimensions) > MAX_DIMENSIONS:
        raise errors.validation_failed(f"dimension 은 최대 {MAX_DIMENSIONS}개입니다.")

    filters = [_bind_filter(catalog, measure, f) for f in query.filters]
    if len(filters) > MAX_FILTERS:
        raise errors.validation_failed(f"filter 는 최대 {MAX_FILTERS}개입니다.")

    project_ids = _resolve_scope(allowed_project_ids, query.projectScope)
    options = spec.options or WidgetOptions()
    limit = min(query.limit or DEFAULT_LIMIT, row_cap(spec.template))
    if limit < 1:
        raise errors.validation_failed("limit 은 1 이상이어야 합니다.")
    # 템플릿의 입력 계약(ARC-012). 차원 초과와 기간축 필수만 굳게 막는다.
    # 나머지는 고를 때(generation·routing) 바로잡는다.
    time_keys = {d.key for d in dimensions if d.value_type == "TIME"}
    unfit = fits(
        spec.template, measure.value_type, [d.key for d in dimensions], time_keys, strict=False
    )
    if unfit is not None:
        raise errors.validation_failed(unfit)

    return ValidatedSpec(
        template=spec.template,
        title=spec.title or measure.label,
        measure=measure,
        dimensions=dimensions,
        filters=filters,
        project_ids=project_ids,
        options=options,
        limit=limit,
        catalog=catalog,
    )


def _bind_filter(catalog: Catalog, measure: MeasureDef, raw: WidgetFilter) -> BoundFilter:
    key = filter_key(raw.field, raw.op)
    if key not in measure.allowed_filters:
        raise catalog_error(f"measure 가 허용하지 않는 filter: {key}")
    definition = catalog.filter(key)
    if definition is None:
        raise catalog_error(f"알 수 없는 filter: {key}")
    values = raw.value if isinstance(raw.value, list) else [raw.value]
    if not values or any(v is None for v in values):
        raise catalog_error(f"filter 값이 비어 있습니다: {key}")
    return BoundFilter(definition, [_cast(definition, v) for v in values])


def _cast(definition: FilterDef, value: Any) -> Any:
    kind = definition.value_type
    text = str(value)
    if kind == "ENUM_LIST":
        if text not in definition.enum_values:
            raise catalog_error(f"허용 목록에 없는 값입니다: {text} (field={definition.field})")
        return text
    if kind == "UUID_LIST":
        try:
            return str(UUID(text))
        except ValueError as exc:
            raise catalog_error(f"UUID 값이 올바르지 않습니다: {text}") from exc
    if kind == "INT":
        try:
            n = int(text)
        except ValueError as exc:
            raise catalog_error(f"정수 값이 올바르지 않습니다: {text}") from exc
        if n < 1:
            raise catalog_error("기간 일수는 1 이상이어야 합니다.")
        return n
    if kind == "DATE_RANGE":
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise catalog_error(f"날짜 값이 올바르지 않습니다: {text}") from exc
    if kind == "MONTH_TOKEN":
        if text.lower() == "current":
            return date.today().replace(day=1)
        try:
            return date.fromisoformat(f"{text}-01")
        except ValueError as exc:
            raise catalog_error(f"월 값이 올바르지 않습니다(YYYY-MM 또는 current): {text}") from exc
    return text


def _resolve_scope(allowed: list[str], requested: list[str]) -> list[str]:
    """요청 범위와 접근 가능 범위의 교집합. 요청이 비면 접근 가능한 전부다."""
    if not requested:
        if not allowed:
            raise errors.project_access_denied()
        return list(allowed)
    scope = [p for p in requested if p in allowed]
    if not scope:
        raise errors.project_access_denied()
    return scope


# ---------------------------------------------------------------- build


def build(spec: ValidatedSpec, dimensions: list[DimensionDef] | None = None) -> BuiltQuery:
    """검증된 명세를 SQL 로 조립한다. dimensions 를 넘기면 그 차원으로 대신 집계한다
    (합계 계산은 차원 없이 한 번 더 돈다)."""
    measure = spec.measure
    dims = spec.dimensions if dimensions is None else dimensions
    time_col = TIME_COLUMNS[measure.base_table]

    joins: dict[str, str] = {}
    _add_joins(joins, measure.join_clause)
    for d in dims:
        _add_joins(joins, d.requires_join)

    select: list[str] = []
    group_by: list[str] = []
    columns: list[WidgetColumn] = []
    time_alias: str | None = None
    for i, d in enumerate(dims):
        alias = f"d{i}"
        select.append(f"{_sql(d.select_expr, time_col)} as {alias}")
        group_by.append(alias)
        columns.append(WidgetColumn(key=alias, label=d.label, type=_dimension_type(d)))
        if d.value_type == "TIME" and time_alias is None:
            time_alias = alias
        if d.label_expr:
            label_alias = f"{alias}_label"
            select.append(f"{_sql(d.label_expr, time_col)} as {label_alias}")
            group_by.append(label_alias)
            columns.append(WidgetColumn(key=label_alias, label=f"{d.label} 명", type="string"))
    select.append(f"{_sql(measure.value_expr, time_col)} as value")
    columns.append(WidgetColumn(key="value", label=measure.label, type=_value_type(measure)))
    # 비율 지표는 분자·분모를 같이 센다. 열 목록에는 넣지 않는다. 차트가 값만 그려야 한다
    if measure.numerator_expr and measure.denominator_expr:
        select.append(f"{_sql(measure.numerator_expr, time_col)} as numerator")
        select.append(f"{_sql(measure.denominator_expr, time_col)} as denominator")

    params: dict[str, Any] = {"projects": list(spec.project_ids)}
    where = ["e.project_id = any(%(projects)s::uuid[])"]
    if measure.row_filter:
        where.append(f"({_sql(measure.row_filter, time_col)})")
    for i, bound in enumerate(spec.filters):
        fragment, bound_params = _filter_fragment(bound, time_col, i)
        where.append(f"({fragment})")
        params.update(bound_params)
        # 필터 컬럼이 다른 별칭(tc. 등)을 쓰면 그 별칭을 만드는 조인이 있어야 한다.
        for alias_join in _joins_for_aliases(bound.definition.column_expr, spec):
            _add_joins(joins, alias_join)

    sql = f"select {', '.join(select)} from {measure.base_table} e"
    for join in joins.values():
        sql += f" {_sql(join, time_col)}"
    sql += " where " + " and ".join(where)
    if group_by:
        sql += " group by " + ", ".join(group_by)

    # 한 줄 더 읽어 잘렸는지 안다. 잘림 표시는 화면이 "상위 N건" 배지로 쓴다.
    params["limit"] = spec.limit + 1
    if time_alias is not None:
        # 시계열은 최근 구간이 살아야 한다. 오래된 것부터 자르면 추이 그림이 과거에 멈춘다.
        others = [g for g in group_by if g != time_alias]
        inner_order = ", ".join([f"{time_alias} desc", *others])
        outer_order = ", ".join([f"{time_alias} asc", *others])
        sql = (
            f"select * from ({sql} order by {inner_order} limit %(limit)s) t"
            f" order by {outer_order}"
        )
    else:
        direction = "asc" if (spec.options.sort or "").lower() == "asc" else "desc"
        order = [f"value {direction} nulls last", *group_by]
        sql += " order by " + ", ".join(order) + " limit %(limit)s"

    return BuiltQuery(sql=sql, params=params, columns=columns)


def _sql(fragment: str, time_col: str) -> str:
    """카탈로그 조각을 넣을 때 자리표시자만 바꾼다. % 는 psycopg 형식 문자라 이스케이프한다."""
    return fragment.replace(_TIME_COL, time_col).replace("%", "%%")


def _filter_fragment(bound: BoundFilter, time_col: str, index: int) -> tuple[str, dict[str, Any]]:
    definition = bound.definition
    column = definition.column_expr.replace(_TIME_COL, time_col).replace("%", "%%")
    name = f"p{index}"
    values = bound.values
    op = definition.op
    if op == "IN":
        cast = "::uuid[]" if definition.value_type == "UUID_LIST" else "::text[]"
        return f"{column} = any(%({name})s{cast})", {name: list(values)}
    if op == "EQ":
        return f"{column} = %({name})s", {name: values[0]}
    if op == "GTE":
        return f"{column} >= %({name})s", {name: values[0]}
    if op == "LTE":
        return f"{column} <= %({name})s", {name: values[0]}
    if op == "BETWEEN":
        if len(values) != 2:
            raise catalog_error("BETWEEN 필터는 시작·종료 값 2개가 필요합니다.")
        lo, hi = sorted(values)
        # 종료일 하루를 포함한다. timestamptz 컬럼에 날짜를 그대로 비교하면 종료일이 빠진다.
        return (
            f"{column} >= %({name}_lo)s::date and {column} < %({name}_hi)s::date + 1",
            {f"{name}_lo": lo, f"{name}_hi": hi},
        )
    if op == "IN_MONTH":
        return (
            f"date_trunc('month', {column}) = date_trunc('month', %({name})s::date)",
            {name: values[0]},
        )
    if op == "LAST_N_DAYS":
        return (
            f"{column} >= current_date - make_interval(days => %({name})s)",
            {name: int(values[0])},
        )
    raise catalog_error(f"지원하지 않는 filter op: {op}")


def _joins_for_aliases(column_expr: str, spec: ValidatedSpec) -> list[str]:
    """필터 컬럼이 e. 가 아닌 별칭을 쓰면, 그 별칭을 정의하는 차원의 조인을 찾아 준다.
    별칭은 카탈로그 차원 정의에서만 나온다."""
    aliases = {a for a in re.findall(r"\b([a-z_]+)\.", column_expr) if a != "e"}
    if not aliases:
        return []
    needed: list[str] = []
    for d in spec.catalog.active_dimensions():
        if d.requires_join and any(_defines_alias(d.requires_join, a) for a in aliases):
            needed.append(d.requires_join)
    return needed


def _defines_alias(join_clause: str, alias: str) -> bool:
    return any(_join_alias(f) == alias for f in _split_joins(join_clause))


def _add_joins(joins: dict[str, str], clause: str | None) -> None:
    if not clause or not clause.strip():
        return
    for fragment in _split_joins(clause):
        joins.setdefault(_join_alias(fragment), fragment)


def _split_joins(clause: str) -> list[str]:
    starts = [m.start() for m in _JOIN_START.finditer(clause)]
    if not starts:
        raise catalog_error(f"join 절을 해석할 수 없습니다: {clause}")
    ends = starts[1:] + [len(clause)]
    return [clause[s:e].strip() for s, e in zip(starts, ends, strict=True)]


def _join_alias(fragment: str) -> str:
    m = _JOIN_START.search(fragment)
    if m is None:
        raise catalog_error(f"join 절을 해석할 수 없습니다: {fragment}")
    tokens = fragment[m.end():].split()
    if not tokens:
        raise catalog_error(f"join 대상 테이블을 찾을 수 없습니다: {fragment}")
    table = tokens[0].rsplit(".", 1)[-1]
    if len(tokens) == 1 or tokens[1].lower() in ("on", "using") or tokens[1].startswith("("):
        return table
    if tokens[1].lower() == "as" and len(tokens) > 2:
        return tokens[2]
    return tokens[1]


def _dimension_type(d: DimensionDef) -> str:
    return "date" if d.value_type == "TIME" else "string"


def _value_type(m: MeasureDef) -> str:
    return "percent" if m.value_type in ("RATE_PCT", "PCT_POINT") else "number"
