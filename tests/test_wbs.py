"""WBS 파서. 용역업체마다 양식이 달라서 관용성이 핵심이다.

DB 가 필요 없다 — 파서는 순수 함수다.
"""

import io
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.dashboard import wbs

HEADERS = ["WBS ID", "업무분류", "산출물", "시작일", "종료일", "가중치", "계획", "실적"]


def build(rows: list[list], headers: list[str] = HEADERS, preamble: int = 0) -> bytes:
    """xlsx 를 만들어 바이트로 돌려준다. preamble 은 머리글 위에 붙는 표지 행 수."""
    wb = Workbook()
    ws = wb.active
    for _ in range(preamble):
        ws.append(["사업명 등 표지"])
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_leaves_only_and_weight_sum() -> None:
    """가중치가 있는 행만 말단이다. 상위 항목은 말단의 합이라 따로 세지 않는다."""
    data = build(
        [
            ["1", "사업관리", "", "2026-01-01", "2026-03-31", None, None, None],
            ["1.1", "착수", "계획서.md", "2026-01-01", "2026-01-10", 0.4, None, 1.0],
            ["1.2", "보고", "보고서.md", "2026-02-01", "2026-02-28", 0.6, None, 0.5],
        ]
    )
    plan = wbs.parse(data)

    assert plan.leaf_count == 2
    assert plan.weight_total == pytest.approx(1.0)
    assert plan.warnings == []
    assert [r.wbs_id for r in plan.rows] == ["1.1", "1.2"]


def test_header_is_found_below_a_title_block() -> None:
    """표지가 위에 붙는 양식이 흔하다. 머리글이 4행에 있다고 가정하면 안 된다."""
    data = build(
        [["1.1", "착수", "", "2026-01-01", "2026-01-10", 1.0, None, 1.0]], preamble=6
    )
    assert wbs.parse(data).leaf_count == 1


def test_column_names_vary_by_vendor() -> None:
    """「작업명」·「비중」·「달성률」로 써도 같은 열로 본다."""
    data = build(
        [["A", "설계", "설계서", "2026-01-01", "2026-02-01", 1.0, None, 0.25]],
        headers=["번호", "작업명", "결과물", "착수일", "완료일", "비중", "계획율", "달성률"],
    )
    plan = wbs.parse(data)

    assert plan.leaf_count == 1
    assert plan.rows[0].actual == pytest.approx(0.25)
    assert plan.rows[0].name == "설계"


@pytest.mark.parametrize("written,expected", [(0.3, 0.3), (30, 0.3), ("30%", 0.3), (100, 1.0)])
def test_percent_notation_is_absorbed(written: object, expected: float) -> None:
    """0.3 · 30 · 30% 가 모두 30% 다. 1 을 넘으면 백분율로 본다."""
    data = build([["1.1", "작업", "", "2026-01-01", "2026-02-01", 1.0, None, written]])
    assert wbs.parse(data).rows[0].actual == pytest.approx(expected)


def test_planned_line_is_recomputed_not_trusted() -> None:
    """파일의 「계획」 열은 자기신고다. 기간으로 다시 계산하고 파일 값은 따로 남긴다."""
    data = build(
        [
            # 100일 중 50일 경과 → 계획 50%. 파일에는 90% 라고 적혀 있다.
            ["1.1", "작업", "", "2026-01-01", "2026-04-11", 1.0, 0.9, 0.2],
        ]
    )
    result = wbs.progress(wbs.parse(data), at=date(2026, 2, 20))

    assert result.planned == pytest.approx(0.5, abs=0.01)
    assert result.declared_planned == pytest.approx(0.9)
    assert result.actual == pytest.approx(0.2)
    assert result.deviation == pytest.approx(-0.3, abs=0.01)


def test_planned_line_clamps_outside_the_period() -> None:
    data = build([["1.1", "작업", "", "2026-05-01", "2026-05-31", 1.0, None, 0.0]])
    plan = wbs.parse(data)

    assert wbs.progress(plan, at=date(2026, 4, 1)).planned == 0.0
    assert wbs.progress(plan, at=date(2026, 12, 1)).planned == 1.0


def test_weight_sum_off_one_warns_and_normalizes() -> None:
    """합이 1이 아니어도 산정은 성립해야 한다. 다만 말은 해 준다."""
    data = build(
        [
            ["1.1", "가", "", "2026-01-01", "2026-02-01", 3.0, None, 1.0],
            ["1.2", "나", "", "2026-01-01", "2026-02-01", 1.0, None, 0.0],
        ]
    )
    plan = wbs.parse(data)
    assert any("가중치 합" in w for w in plan.warnings)
    # 3:1 가중이므로 75%. 합으로 나눠 정규화한 결과다.
    assert wbs.progress(plan, at=date(2026, 1, 1)).actual == pytest.approx(0.75)


def test_unreadable_actual_warns_and_counts_as_zero() -> None:
    """조용히 틀린 수치를 내는 것보다 못 읽었다고 말하는 편이 낫다."""
    data = build([["1.1", "작업", "", "2026-01-01", "2026-02-01", 1.0, None, "진행중"]])
    plan = wbs.parse(data)

    assert plan.rows[0].actual == 0.0
    assert any("실적을 숫자로 읽지 못해" in w for w in plan.warnings)


def test_reversed_period_warns_and_drops_the_dates() -> None:
    data = build([["1.1", "작업", "", "2026-05-01", "2026-01-01", 1.0, None, 0.0]])
    plan = wbs.parse(data)

    assert any("종료일이 시작일보다" in w for w in plan.warnings)
    assert plan.rows[0].start is None


def test_behind_lists_leaves_under_the_plan_line() -> None:
    data = build(
        [
            ["1.1", "늦은 작업", "", "2026-01-01", "2026-02-01", 0.5, None, 0.0],
            ["1.2", "끝난 작업", "", "2026-01-01", "2026-02-01", 0.5, None, 1.0],
        ]
    )
    result = wbs.progress(wbs.parse(data), at=date(2026, 3, 1))

    assert result.behind == ["1.1 늦은 작업"]


def test_missing_header_raises() -> None:
    data = build([["아무", "값"]], headers=["갑", "을"])
    with pytest.raises(wbs.WbsParseError, match="머리글"):
        wbs.parse(data)


def test_no_leaf_raises() -> None:
    data = build([["1", "상위만 있다", "", "2026-01-01", "2026-02-01", None, None, None]])
    with pytest.raises(wbs.WbsParseError, match="말단"):
        wbs.parse(data)


def test_not_an_excel_file_raises() -> None:
    with pytest.raises(wbs.WbsParseError, match="엑셀"):
        wbs.parse("이건 xlsx 가 아니다".encode())


def test_our_own_wbs_parses() -> None:
    """자기참조 프로젝트의 실제 기준선. 이게 안 읽히면 시연이 성립하지 않는다."""
    path = Path(__file__).resolve().parent.parent / "docs" / "00-management" / "WBS.xlsx"
    if not path.exists():
        pytest.skip("WBS.xlsx 가 없다")

    plan = wbs.parse(path.read_bytes())

    assert plan.leaf_count >= 30
    assert plan.weight_total == pytest.approx(1.0, abs=0.005)
    assert plan.warnings == []

    result = wbs.progress(plan, at=date(2026, 9, 8))
    assert 0.0 < result.actual < 1.0
    assert 0.0 < result.planned < 1.0
