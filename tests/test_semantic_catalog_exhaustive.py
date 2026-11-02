"""카탈로그 전수 실행 (SWFR.WEB.001 · GH-69, 파일럿 설계검증 HIGH-3).

마이그레이션이 넣은 실제 카탈로그를 읽어, 쓰고 있는 지표마다 허용된 차원(없음·하나·둘)과
허용된 필터를 하나씩 붙인 SQL 을 조립하고 시험 DB 에 실제로 던진다. 조립 결함(라벨식이 GROUP BY
에서 빠짐, 필터 별칭의 조인 누락, 시간 컬럼 치환 실수)은 단위 시험의 손 카탈로그로는 안 보이고
DB 가 문장을 받아 봐야 드러난다. 값은 보지 않는다. 문장이 실행되는지와 열 모양만 본다.

카탈로그에 지표·차원·필터를 더하면 이 시험이 새 조합을 저절로 돌린다.
"""

from itertools import combinations
from typing import Any

from app.db import fetch_all, tx
from app.semantic import builder
from app.semantic import catalog as catalog_module
from app.semantic.catalog import Catalog, DimensionDef, FilterDef, MeasureDef
from app.semantic.models import WidgetOptions
from tests.conftest import requires_db

PID = "c0000000-0000-4000-8000-000000000001"

# 필터 값 꼴마다 하나씩. 값이 맞는지는 보지 않고 문장이 실행되는지만 본다
_SAMPLE: dict[str, list[Any]] = {
    "UUID_LIST": [PID],
    "INT": [30],
    "DATE_RANGE": ["2026-08-01", "2026-11-30"],
    "MONTH_TOKEN": ["current"],
}


def _values(definition: FilterDef) -> list[Any]:
    if definition.value_type == "ENUM_LIST":
        return [definition.enum_values[0]]
    sample = _SAMPLE.get(definition.value_type, ["x"])
    return sample if definition.op == "BETWEEN" else sample[:1]


def _bound(definition: FilterDef) -> builder.BoundFilter:
    values = [builder._cast(definition, v) for v in _values(definition)]
    return builder.BoundFilter(definition, values)


def _spec(
    catalog: Catalog, measure: MeasureDef, dims: list[DimensionDef],
    filters: list[builder.BoundFilter],
) -> builder.ValidatedSpec:
    return builder.ValidatedSpec(
        template="TABLE", title=measure.label, measure=measure, dimensions=dims,
        filters=filters, project_ids=[PID], options=WidgetOptions(), limit=10, catalog=catalog,
    )


def _cases(catalog: Catalog) -> list[tuple[str, builder.ValidatedSpec]]:
    cases = []
    for m in sorted(catalog.active_measures(), key=lambda m: m.key):
        dims = [d for k in m.allowed_dimensions if (d := catalog.dimension(k)) is not None]
        for n in (0, 1, 2):
            for combo in combinations(dims, n):
                # 시간 축 둘은 템플릿이 받지 않는다(ARC-012). 조립 대상이 아니다
                if sum(d.value_type == "TIME" for d in combo) > 1:
                    continue
                label = "+".join(d.key for d in combo) or "-"
                cases.append((f"{m.key}[{label}]", _spec(catalog, m, list(combo), [])))
        for key in m.allowed_filters:
            f = catalog.filter(key)
            if f is None:
                continue
            first = dims[:1]
            cases.append((f"{m.key}[{key}]", _spec(catalog, m, first, [_bound(f)])))
    return cases


@requires_db
def test_카탈로그의_모든_지표_차원_필터_조합이_실행된다():
    with tx() as cur:
        catalog = catalog_module.load(cur)
        cases = _cases(catalog)
        assert len(catalog.active_measures()) >= 10, "카탈로그가 비었다. 마이그레이션을 확인"

        failed: list[str] = []
        for name, spec in cases:
            query = builder.build(spec)
            try:
                with cur.connection.transaction():
                    rows = fetch_all(cur, query.sql, query.params)
            except Exception as exc:  # noqa: BLE001 — 실패한 조합을 모두 모아 한 번에 보인다
                failed.append(f"{name}: {type(exc).__name__}: {str(exc).splitlines()[0]}")
                continue
            keys = {c.key for c in query.columns}
            for row in rows:
                missing = keys - set(row)
                if missing:
                    failed.append(f"{name}: 열 {sorted(missing)} 이 결과에 없다")
                    break
        assert not failed, f"{len(failed)}/{len(cases)} 조합 실패\n" + "\n".join(failed)


@requires_db
def test_라벨식이_있는_차원은_선택과_묶음에_같은_식이_들어간다():
    """HIGH-3 의 원래 지적. 라벨식을 SELECT 에만 넣으면 집계 문장이 거부된다."""
    with tx() as cur:
        catalog = catalog_module.load(cur)
    labelled = [d for d in catalog.active_dimensions() if d.label_expr]
    assert labelled, "라벨식 있는 차원이 없다. 시험이 아무것도 보지 않는다"
    for d in labelled:
        m = next((m for m in catalog.active_measures() if d.key in m.allowed_dimensions), None)
        if m is None:
            continue
        built = builder.build(_spec(catalog, m, [d], []))
        assert "d0_label" in built.sql.split(" group by ")[1], d.key


def test_시간_축_둘인_조합은_건너뛴다():
    t = DimensionDef("period_month", "월", "", "x", None, None, "TIME", "ACTIVE")
    c = DimensionDef("project", "사업", "", "y", None, None, "CATEGORY", "ACTIVE")
    w = DimensionDef("period_week", "주", "", "z", None, None, "TIME", "ACTIVE")
    cat = Catalog()
    cat.dimensions = {d.key: d for d in (t, c, w)}
    cat.measures["m"] = MeasureDef(
        key="m", label="m", description="", base_table="issue", join_clause=None,
        row_filter=None, value_expr="count(*)", value_type="COUNT", unit=None,
        allowed_dimensions=("period_month", "project", "period_week"), allowed_filters=(),
        default_dimension=None, target_value=None, status="ACTIVE",
    )
    names = [n for n, _ in _cases(cat)]
    assert "m[period_month+period_week]" not in names
    assert "m[period_month+project]" in names
    assert len(names) == 1 + 3 + 2

