"""위젯 데이터 산출. 명세 → 검증 → 조립 → 실행 → 응답 조립.

메뉴 화면과 자연어 질의가 같은 run() 을 부른다. 두 경로의 수치가 어긋나면 그건 버그다.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.auth import repository as auth_repo
from app.auth.models import AuthPrincipal
from app.db import fetch_all
from app.semantic import builder
from app.semantic import catalog as catalog_module
from app.semantic.builder import BoundFilter, ValidatedSpec
from app.semantic.models import (
    SemanticCatalogResponse,
    SemanticDimensionResponse,
    SemanticFilterResponse,
    SemanticMeasureResponse,
    WidgetDataResponse,
    WidgetFilter,
    WidgetRow,
    WidgetSpec,
)

# 차원별 값 옆에 "전체" 값이 있어야 읽히는 그림. 숫자 카드는 그 값이 본체고,
# 진행 목록은 그 값을 기준선으로 긋는다.
_TOTAL_TEMPLATES = frozenset({"STAT_CARD", "PROGRESS_LIST", "BULLET_CHART"})


def run(
    cur: Any,
    principal: AuthPrincipal,
    spec: WidgetSpec,
    project_scope_override: list[str] | None = None,
    period_override: WidgetFilter | None = None,
) -> WidgetDataResponse:
    allowed = auth_repo.allowed_project_ids(
        cur, principal.role, principal.org_id, principal.user_id
    )
    effective = _apply_override(spec, project_scope_override, period_override)
    catalog = catalog_module.load(cur)
    validated = builder.validate(catalog, effective, allowed)
    return run_validated(cur, validated)


def run_validated(cur: Any, validated: ValidatedSpec) -> WidgetDataResponse:
    query = builder.build(validated)
    raw = fetch_all(cur, query.sql, query.params)
    truncated = len(raw) > validated.limit
    rows = [WidgetRow(values=_plain(r)) for r in raw[: validated.limit]]

    total: WidgetRow | None = None
    if validated.template in _TOTAL_TEMPLATES:
        total = rows[0] if not validated.dimensions and rows else _total(cur, validated)

    previous: WidgetRow | None = None
    if validated.options.compareWithPrevious and not validated.dimensions:
        previous = _previous_total(cur, validated)

    measure = validated.measure
    return WidgetDataResponse(
        measure=measure.key,
        measureLabel=measure.label,
        unit=measure.unit,
        dimensions=[d.key for d in validated.dimensions],
        columns=query.columns,
        rows=rows,
        total=total,
        previousTotal=previous,
        target=measure.target_value,
        appliedProjectIds=list(validated.project_ids),
        truncated=truncated,
        basis=validated.measure.basis,
        generatedAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def catalog_response(cur: Any) -> SemanticCatalogResponse:
    catalog = catalog_module.load(cur)
    return SemanticCatalogResponse(
        measures=[
            SemanticMeasureResponse(
                key=m.key,
                label=m.label,
                description=m.description,
                unit=m.unit,
                allowedDimensions=list(m.allowed_dimensions),
                allowedFilters=list(m.allowed_filters),
                defaultTemplates=_default_templates(m.value_type, m.default_dimension),
                status=m.status,
            )
            for m in catalog.active_measures()
        ],
        dimensions=[
            SemanticDimensionResponse(
                key=d.key,
                label=d.label,
                description=d.description,
                valueType=d.value_type,
                enumValues=[],
                status=d.status,
            )
            for d in catalog.active_dimensions()
        ],
        filters=[
            SemanticFilterResponse(
                key=f.key,
                field=f.field,
                op=f.op,
                label=f.label,
                valueType=f.value_type,
                enumValues=list(f.enum_values),
                status=f.status,
            )
            for f in catalog.active_filters()
        ],
    )


def _default_templates(value_type: str, default_dimension: str | None) -> list[str]:
    if default_dimension and default_dimension.startswith("period_"):
        return ["LINE_CHART", "AREA_CHART", "STAT_CARD"]
    if value_type in ("RATE_PCT", "PCT_POINT"):
        return ["STAT_CARD", "PROGRESS_LIST", "BAR_CHART"]
    return ["STAT_CARD", "BAR_CHART", "PIE_CHART"]


def _total(cur: Any, validated: ValidatedSpec) -> WidgetRow | None:
    """차원 없이 한 번 더 집계한 전체 값."""
    query = builder.build(validated, dimensions=[])
    raw = fetch_all(cur, query.sql, query.params)
    return WidgetRow(values=_plain(raw[0])) if raw else None


def _previous_total(cur: Any, validated: ValidatedSpec) -> WidgetRow | None:
    """직전 같은 길이 구간의 전체 값. 기간 필터가 최근 N일·구간일 때만 정의된다."""
    shifted = _shift_period(validated)
    if shifted is None:
        return None
    query = builder.build(shifted, dimensions=[])
    raw = fetch_all(cur, query.sql, query.params)
    return WidgetRow(values=_plain(raw[0])) if raw else None


def _shift_period(validated: ValidatedSpec) -> ValidatedSpec | None:
    for i, bound in enumerate(validated.filters):
        definition = bound.definition
        if definition.field != "period":
            continue
        between = validated.catalog.filter("period__between")
        if between is None:
            return None
        if definition.op == "LAST_N_DAYS":
            n = int(bound.values[0])
            hi = date.today() - timedelta(days=n + 1)
            lo = hi - timedelta(days=n - 1)
        elif definition.op == "BETWEEN":
            lo0, hi0 = sorted(bound.values)
            span = (hi0 - lo0).days + 1
            hi = lo0 - timedelta(days=1)
            lo = hi - timedelta(days=span - 1)
        else:
            return None
        filters = list(validated.filters)
        filters[i] = BoundFilter(between, [lo, hi])
        return ValidatedSpec(
            template=validated.template,
            title=validated.title,
            measure=validated.measure,
            dimensions=[],
            filters=filters,
            project_ids=validated.project_ids,
            options=validated.options,
            limit=validated.limit,
            catalog=validated.catalog,
        )
    return None


def _apply_override(
    spec: WidgetSpec, project_scope: list[str] | None, period: WidgetFilter | None
) -> WidgetSpec:
    if not project_scope and period is None:
        return spec
    query = spec.query.model_copy(deep=True)
    if project_scope:
        query.projectScope = list(project_scope)
    if period is not None:
        query.filters = [f for f in query.filters if f.field != "period"] + [period]
    return spec.model_copy(update={"query": query})


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    """psycopg 가 준 값을 JSON 이 되는 값으로. Decimal 은 float, 날짜는 ISO 문자열."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, datetime | date):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out
