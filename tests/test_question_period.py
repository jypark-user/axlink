"""질문의 기간 표현 → 집계 필터 (GH-123, QUR.RAG.002). 모델 없이 도는 단위 시험이다."""

from datetime import date

import pytest

from app.rag import question_period as qp
from app.semantic.catalog import MeasureDef

TODAY = date(2026, 1, 14)


def _measure(*filters: str) -> MeasureDef:
    return MeasureDef(
        key="progress_representative_pct", label="대표 진척률", description="",
        base_table="progress_snapshot", join_clause=None, row_filter=None, value_expr="avg(x)",
        value_type="RATE_PCT", unit="%", allowed_dimensions=("period_day",),
        allowed_filters=filters, default_dimension=None, target_value=None, status="ACTIVE",
    )


SNAPSHOT = _measure("project_id__in", "period__in_month", "period__last_n_days")


@pytest.mark.parametrize(
    ("question", "op", "value"),
    [
        ("이번 달 진척 추세 보여줘", "IN_MONTH", "current"),
        ("이번달 진척률", "IN_MONTH", "current"),
        ("당월 진척률은?", "IN_MONTH", "current"),
        ("지난달 진척 추세", "IN_MONTH", "2025-12"),  # 1월이면 앞해 12월
        ("최근 30일 진척률 변화", "LAST_N_DAYS", 30),
        ("최근 2주 진척", "LAST_N_DAYS", 14),
    ],
)
def test_정해진_기간_표현을_필터로_읽는다(question, op, value):
    f = qp.filter_for(question, SNAPSHOT, TODAY)
    assert f is not None
    assert (f.field, f.op, f.value) == ("period", op, value)


def test_기간_표현이_없으면_필터를_붙이지_않는다():
    assert qp.filter_for("진척 추세 보여줘", SNAPSHOT, TODAY) is None
    assert qp.filter_for("이번 주 진척", SNAPSHOT, TODAY) is None  # 주 단위는 읽지 않는다


def test_지표가_허용하지_않는_필터는_붙이지_않는다():
    wbs = _measure("project_id__in")
    assert qp.filter_for("이번 달 WBS 완료율", wbs, TODAY) is None
    only_days = _measure("period__last_n_days")
    assert qp.filter_for("이번 달 진척", only_days, TODAY) is None
    assert qp.filter_for("최근 7일 진척", only_days, TODAY).value == 7


def test_표현이_둘이면_앞에_나온_것을_쓴다():
    f = qp.filter_for("최근 7일과 이번 달을 비교", SNAPSHOT, TODAY)
    assert (f.op, f.value) == ("LAST_N_DAYS", 7)
