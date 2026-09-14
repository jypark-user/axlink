"""시맨틱 레이어 조립 (SWFR.WEB.001 · 절대 규칙 1).

DB 없이 카탈로그를 손으로 만들어 본다. 보려는 것은 두 가지다.
카탈로그에 없는 것은 조립 전에 막히는가, SQL 에 들어가는 문자열이 카탈로그 조각뿐인가.
"""

from datetime import date

import pytest

from app.common import errors
from app.semantic import builder
from app.semantic.catalog import Catalog, DimensionDef, FilterDef, MeasureDef
from app.semantic.models import WidgetFilter, WidgetOptions, WidgetQuery, WidgetSpec

PID = "c0000000-0000-4000-8000-000000000001"
OTHER = "c0000000-0000-4000-8000-000000000002"


def _catalog() -> Catalog:
    cat = Catalog()
    cat.measures["open_issue_count"] = MeasureDef(
        key="open_issue_count", label="열린 이슈 수", description="", base_table="issue",
        join_clause=None, row_filter="e.status in ('OPEN','IN_PROGRESS')", value_expr="count(*)",
        value_type="COUNT", unit="건",
        allowed_dimensions=("project", "issue_severity", "contractor_org", "period_month"),
        allowed_filters=("project_id__in", "issue_severity__in", "period__last_n_days",
                         "period__between", "contractor_org_id__in"),
        default_dimension="issue_severity", target_value=None, status="ACTIVE",
    )
    cat.measures["retired"] = MeasureDef(
        key="retired", label="폐기", description="", base_table="issue", join_clause=None,
        row_filter=None, value_expr="count(*)", value_type="COUNT", unit="건",
        allowed_dimensions=(), allowed_filters=(), default_dimension=None, target_value=None,
        status="DEPRECATED",
    )
    cat.dimensions["project"] = DimensionDef(
        key="project", label="프로젝트", description="", select_expr="e.project_id::text",
        label_expr="p.name", requires_join="join project p on p.id = e.project_id",
        value_type="CATEGORY", status="ACTIVE",
    )
    cat.dimensions["issue_severity"] = DimensionDef(
        key="issue_severity", label="이슈 심각도", description="", select_expr="e.severity",
        label_expr=None, requires_join=None, value_type="CATEGORY", status="ACTIVE",
    )
    cat.dimensions["contractor_org"] = DimensionDef(
        key="contractor_org", label="용역사", description="",
        select_expr="coalesce(tc.contractor_org_id::text, 'UNASSIGNED')",
        label_expr="coalesce(o.name, '미지정')",
        requires_join="left join tool_connection tc on tc.id = e.tool_connection_id "
                      "left join organization o on o.id = tc.contractor_org_id",
        value_type="CATEGORY", status="ACTIVE",
    )
    cat.dimensions["period_month"] = DimensionDef(
        key="period_month", label="월", description="",
        select_expr="to_char(date_trunc('month', <TIME_COL>), 'YYYY-MM')",
        label_expr=None, requires_join=None, value_type="TIME", status="ACTIVE",
    )
    cat.filters["project_id__in"] = FilterDef(
        key="project_id__in", field="project_id", op="IN", label="", description="",
        column_expr="e.project_id", value_type="UUID_LIST", enum_values=(), status="ACTIVE",
    )
    cat.filters["issue_severity__in"] = FilterDef(
        key="issue_severity__in", field="issue_severity", op="IN", label="", description="",
        column_expr="e.severity", value_type="ENUM_LIST",
        enum_values=("BLOCKER", "CRITICAL", "MAJOR"), status="ACTIVE",
    )
    cat.filters["period__last_n_days"] = FilterDef(
        key="period__last_n_days", field="period", op="LAST_N_DAYS", label="", description="",
        column_expr="<TIME_COL>", value_type="INT", enum_values=(), status="ACTIVE",
    )
    cat.filters["period__between"] = FilterDef(
        key="period__between", field="period", op="BETWEEN", label="", description="",
        column_expr="<TIME_COL>", value_type="DATE_RANGE", enum_values=(), status="ACTIVE",
    )
    cat.filters["contractor_org_id__in"] = FilterDef(
        key="contractor_org_id__in", field="contractor_org_id", op="IN", label="",
        description="", column_expr="tc.contractor_org_id", value_type="UUID_LIST",
        enum_values=(), status="ACTIVE",
    )
    return cat


def _spec(measure="open_issue_count", dims=(), filters=(), template="BAR_CHART", **kw):
    return WidgetSpec(
        template=template, title="t",
        query=WidgetQuery(measure=measure, dimensions=list(dims), filters=list(filters),
                          projectScope=[PID], limit=kw.get("limit")),
        options=WidgetOptions(sort=kw.get("sort")),
    )


def test_카탈로그에_없는_지표는_조립_전에_막힌다():
    with pytest.raises(errors.ApiError) as exc:
        builder.validate(_catalog(), _spec(measure="made_up_metric"), [PID])
    assert exc.value.code == "CATALOG_VALIDATION_FAILED"


def test_폐기된_지표도_막힌다():
    with pytest.raises(errors.ApiError):
        builder.validate(_catalog(), _spec(measure="retired"), [PID])


def test_지표가_허용하지_않는_차원은_막힌다():
    with pytest.raises(errors.ApiError) as exc:
        builder.validate(_catalog(), _spec(dims=["work_product_type"]), [PID])
    assert "dimension" in exc.value.message


def test_허용_목록_밖의_enum_값은_막힌다():
    f = WidgetFilter(field="issue_severity", op="IN", value=["MAJOR", "'; drop table issue; --"])
    with pytest.raises(errors.ApiError) as exc:
        builder.validate(_catalog(), _spec(filters=[f]), [PID])
    assert exc.value.code == "CATALOG_VALIDATION_FAILED"


def test_접근_범위_밖의_사업만_요청하면_거부된다():
    spec = _spec()
    spec.query.projectScope = [OTHER]
    with pytest.raises(errors.ApiError) as exc:
        builder.validate(_catalog(), spec, [PID])
    assert exc.value.code == "PROJECT_ACCESS_DENIED"


def test_범위는_요청과_접근_가능의_교집합이다():
    spec = _spec()
    spec.query.projectScope = [OTHER, PID]
    validated = builder.validate(_catalog(), spec, [PID])
    assert validated.project_ids == [PID]


def test_사용자_값은_SQL_이_아니라_파라미터로_간다():
    f = WidgetFilter(field="issue_severity", op="IN", value=["MAJOR"])
    g = WidgetFilter(field="period", op="LAST_N_DAYS", value="30")
    validated = builder.validate(_catalog(), _spec(dims=["issue_severity"], filters=[f, g]), [PID])
    built = builder.build(validated)
    assert "MAJOR" not in built.sql and "30" not in built.sql
    assert built.params["p0"] == ["MAJOR"]
    assert built.params["p1"] == 30
    assert built.params["projects"] == [PID]
    assert "e.project_id = any(%(projects)s::uuid[])" in built.sql
    assert "e.status in ('OPEN','IN_PROGRESS')" in built.sql  # 카탈로그 조각은 그대로
    assert "group by d0" in built.sql


def test_기간_축은_시간_컬럼으로_치환되고_최근_구간이_남는다():
    validated = builder.validate(_catalog(), _spec(dims=["period_month"], limit=12), [PID])
    built = builder.build(validated)
    assert "<TIME_COL>" not in built.sql
    assert "coalesce(e.source_created_at, e.created_at)" in built.sql
    assert "order by d0 desc limit %(limit)s" in built.sql and "order by d0 asc" in built.sql
    assert built.params["limit"] == 13  # 한 줄 더 읽어 잘림을 안다
    assert [c.key for c in built.columns] == ["d0", "value"]
    assert built.columns[0].type == "date"


def test_라벨식이_있는_차원은_label_컬럼이_붙는다():
    validated = builder.validate(_catalog(), _spec(dims=["project"], sort="asc"), [PID])
    built = builder.build(validated)
    assert [c.key for c in built.columns] == ["d0", "d0_label", "value"]
    assert "join project p on p.id = e.project_id" in built.sql
    assert "order by value asc nulls last" in built.sql


def test_필터가_쓰는_별칭의_조인을_찾아_붙인다():
    f = WidgetFilter(field="contractor_org_id", op="IN", value=[PID])
    validated = builder.validate(_catalog(), _spec(filters=[f]), [PID])
    built = builder.build(validated)
    assert built.sql.count("left join tool_connection tc") == 1
    assert "tc.contractor_org_id = any(%(p0)s::uuid[])" in built.sql


def test_같은_조인은_한_번만_붙는다():
    f = WidgetFilter(field="contractor_org_id", op="IN", value=[PID])
    validated = builder.validate(_catalog(), _spec(dims=["contractor_org"], filters=[f]), [PID])
    built = builder.build(validated)
    assert built.sql.count("left join tool_connection tc") == 1
    assert built.sql.count("left join organization o") == 1


def test_구간_필터는_종료일을_포함한다():
    f = WidgetFilter(field="period", op="BETWEEN", value=["2026-03-01", "2026-03-31"])
    validated = builder.validate(_catalog(), _spec(filters=[f]), [PID])
    built = builder.build(validated)
    assert built.params["p0_lo"] == date(2026, 3, 1)
    assert built.params["p0_hi"] == date(2026, 3, 31)
    assert "< %(p0_hi)s::date + 1" in built.sql


def test_행_상한은_템플릿마다_다르다():
    assert builder.validate(_catalog(), _spec(limit=999), [PID]).limit == 100
    assert builder.validate(_catalog(), _spec(template="CHECKLIST", limit=999), [PID]).limit == 200
    assert builder.validate(_catalog(), _spec(), [PID]).limit == 50


def test_차원은_둘까지다():
    with pytest.raises(errors.ApiError):
        three = ["project", "issue_severity", "period_month"]
        builder.validate(_catalog(), _spec(dims=three), [PID])
