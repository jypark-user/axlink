"""카탈로그 읽기. semantic_measure · semantic_dimension · semantic_filter 세 표가 원천이다.

값(SQL 조각)은 마이그레이션이 심는다. 코드에는 조각이 없다. 지표를 늘리는 일은
마이그레이션 한 줄이고 파이썬은 바뀌지 않는다.
"""

from dataclasses import dataclass, field
from typing import Any

from app.db import fetch_all


@dataclass(frozen=True)
class MeasureDef:
    key: str
    label: str
    description: str
    base_table: str
    join_clause: str | None
    row_filter: str | None
    value_expr: str
    value_type: str  # COUNT | RATE_PCT | DAYS | PCT_POINT
    unit: str | None
    allowed_dimensions: tuple[str, ...]
    allowed_filters: tuple[str, ...]
    default_dimension: str | None
    target_value: float | None
    status: str
    basis: str | None = None  # 사람 말 산출 근거. 답변과 위젯이 같이 보인다(QUR.WEB.002)
    numerator_expr: str | None = None  # 비율 지표의 분자. value_expr 와 같은 집계 단위
    denominator_expr: str | None = None


@dataclass(frozen=True)
class DimensionDef:
    key: str
    label: str
    description: str
    select_expr: str
    label_expr: str | None
    requires_join: str | None
    value_type: str  # CATEGORY | TIME
    status: str


@dataclass(frozen=True)
class FilterDef:
    key: str
    field: str
    op: str
    label: str
    description: str
    column_expr: str
    value_type: str  # ENUM_LIST | UUID_LIST | DATE_RANGE | MONTH_TOKEN | INT
    enum_values: tuple[str, ...]
    status: str


@dataclass
class Catalog:
    measures: dict[str, MeasureDef] = field(default_factory=dict)
    dimensions: dict[str, DimensionDef] = field(default_factory=dict)
    filters: dict[str, FilterDef] = field(default_factory=dict)

    def measure(self, key: str) -> MeasureDef | None:
        m = self.measures.get(key)
        return m if m is not None and m.status == "ACTIVE" else None

    def dimension(self, key: str) -> DimensionDef | None:
        d = self.dimensions.get(key)
        return d if d is not None and d.status == "ACTIVE" else None

    def filter(self, key: str) -> FilterDef | None:
        f = self.filters.get(key)
        return f if f is not None and f.status == "ACTIVE" else None

    def active_measures(self) -> list[MeasureDef]:
        return [m for m in self.measures.values() if m.status == "ACTIVE"]

    def active_dimensions(self) -> list[DimensionDef]:
        return [d for d in self.dimensions.values() if d.status == "ACTIVE"]

    def active_filters(self) -> list[FilterDef]:
        return [f for f in self.filters.values() if f.status == "ACTIVE"]


def filter_key(field_name: str, op: str) -> str:
    """semantic_filter.key 규칙. `period` + `LAST_N_DAYS` → `period__last_n_days`."""
    return f"{field_name}__{op.lower()}"


def load(cur: Any) -> Catalog:
    """매 요청마다 읽는다. 세 표 합쳐 60행이 안 되고, 캐시를 두면 마이그레이션 직후 낡은
    카탈로그로 조립하는 문제가 생긴다."""
    catalog = Catalog()
    for r in fetch_all(cur, "select * from semantic_measure order by key"):
        catalog.measures[r["key"]] = MeasureDef(
            key=r["key"],
            label=r["label"],
            description=r["description"],
            base_table=r["base_table"],
            join_clause=r["join_clause"],
            row_filter=r["row_filter"],
            value_expr=r["value_expr"],
            value_type=r["value_type"],
            unit=r["unit"],
            allowed_dimensions=tuple(r["allowed_dimensions"] or ()),
            allowed_filters=tuple(r["allowed_filters"] or ()),
            default_dimension=r["default_dimension"],
            target_value=None if r.get("target_value") is None else float(r["target_value"]),
            status=r["status"],
            basis=r.get("basis"),
            numerator_expr=r.get("numerator_expr"),
            denominator_expr=r.get("denominator_expr"),
        )
    for r in fetch_all(cur, "select * from semantic_dimension order by key"):
        catalog.dimensions[r["key"]] = DimensionDef(
            key=r["key"],
            label=r["label"],
            description=r["description"],
            select_expr=r["select_expr"],
            label_expr=r["label_expr"],
            requires_join=r["requires_join"],
            value_type=r["value_type"],
            status=r["status"],
        )
    for r in fetch_all(cur, "select * from semantic_filter order by key"):
        catalog.filters[r["key"]] = FilterDef(
            key=r["key"],
            field=r["field"],
            op=r["op"],
            label=r["label"],
            description=r["description"],
            column_expr=r["column_expr"],
            value_type=r["value_type"],
            enum_values=tuple(r["enum_values"] or ()),
            status=r["status"],
        )
    return catalog
