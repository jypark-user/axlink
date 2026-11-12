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


def test_인식_결과에_머리글_행과_열_매핑이_남는다() -> None:
    """UC-030 3단계 인식 결과: 어느 열을 무엇으로 읽었는지. 없는 열은 None (DEC-04 (b))."""
    headers = ["업무분류", "가중치(%)", "실적", "종료일"]
    data = build([["착수", 100, 50, "2026-01-10"]], headers=headers, preamble=2)
    plan = wbs.parse(data)
    assert plan.header_row == 3
    by = {c["field"]: c for c in plan.columns}
    assert by["name"] == {"field": "name", "label": "작업명", "header": "업무분류", "column": "A"}
    assert by["weight"]["header"] == "가중치(%)" and by["weight"]["column"] == "B"
    assert by["actual"]["column"] == "C" and by["end"]["column"] == "D"
    assert by["wbs_id"]["header"] is None and by["wbs_id"]["column"] is None
    labels = [c["label"] for c in plan.columns]
    assert labels == ["번호", "작업명", "산출물", "시작일", "종료일", "가중치", "계획", "실적"]


# ---------------------------------------------------------------- L2 (DEC-19)

L2_HEADERS = ["WBS ID", "업무분류", "산출물", "시작일", "종료일", "계획", "실적"]
# IM-009 TD-WBS-L2: 5.1 의 WBS 에서 가중치 열만 뺀 것. 기간 44·106·136·60·29 = 375 일
L2_ROWS = [
    ["3", "수행", "", "2026-03-02", "2026-11-30", "", ""],
    ["3.1", "요구사항 정의", "요구사항정의서", "2026-03-02", "2026-04-15", 1.00, 1.00],
    ["3.2", "설계", "SW설계서", "2026-04-16", "2026-07-31", 1.00, 0.40],
    ["3.3", "구현", "프로그램 목록", "2026-06-01", "2026-10-15", 0.80, 0.20],
    ["3.4", "시험", "시험결과서", "2026-09-01", "2026-10-31", 0.30, 0.00],
    ["3.5", "인도", "사용자매뉴얼", "2026-11-01", "2026-11-30", 0.00, 0.00],
]


def test_l2_weights_by_period_and_actual_from_file() -> None:
    """가중치 열이 없으면 기간 비례 가중치 × 파일 실적. 산출물 제출로 실적을 대신하지 않는다."""
    plan = wbs.parse(build(L2_ROWS, L2_HEADERS))
    assert plan.estimated is True
    assert [r.wbs_id for r in plan.rows] == ["3.1", "3.2", "3.3", "3.4", "3.5"]
    assert [g.wbs_id for g in plan.groups] == ["3"]
    assert [r.weight for r in plan.rows] == [0.117333, 0.282667, 0.362667, 0.16, 0.077333]
    assert any("기간에 비례" in w for w in plan.warnings)

    p = wbs.progress(plan, date(2026, 9, 15))
    # (44×1 + 106×0.4 + 136×0.2) / 375 = 113.6 / 375 = 0.302933
    assert p.actual == 0.3029
    # 경과 일수 (44 + 106 + 106 + 14) / 375 = 0.72
    assert p.planned == 0.72
    assert p.estimated is True and p.unavailable == []


def test_l2_missing_period_or_actual_is_unavailable_with_reason() -> None:
    """기간이나 실적이 모자라면 0% 로 내지 않고 이유를 낸다."""
    rows = [list(r) for r in L2_ROWS]
    rows[4][3] = ""  # 3.4 시작일 없음
    rows[5][6] = ""  # 3.5 실적 없음
    p = wbs.progress(wbs.parse(build(rows, L2_HEADERS)), date(2026, 9, 15))
    assert p.actual is None and p.planned is None and p.deviation is None
    assert any("3.4 시험" in r and "시작일" in r for r in p.unavailable), p.unavailable
    assert any("3.5 인도" in r and "실적" in r for r in p.unavailable), p.unavailable


def test_l2_without_actual_column_is_unavailable() -> None:
    """가중치도 실적 열도 없으면(시작일·종료일만) 계획선은 내고 진척률은 내지 않는다."""
    headers = ["WBS ID", "업무분류", "산출물", "시작일", "종료일", "계획"]
    rows = [r[:6] for r in L2_ROWS]
    with pytest.raises(wbs.WbsParseError):
        wbs.parse(build(rows, headers))  # 가중치·실적 둘 다 없으면 머리글이 아니다
    headers = ["WBS ID", "업무분류", "산출물", "시작일", "종료일", "실적"]
    rows = [r[:5] + [""] for r in L2_ROWS]
    p = wbs.progress(wbs.parse(build(rows, headers)), date(2026, 9, 15))
    assert p.actual is None and p.planned == 0.72
    assert p.unavailable == ["WBS 에 실적이 없습니다(실적 열이 없거나 값이 비었습니다)"]
