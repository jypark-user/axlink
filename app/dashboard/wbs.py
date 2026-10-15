"""WBS 파싱과 진척 산정 (SWFR.PIP.010).

용역업체마다 WBS 양식이 다르다. 그래서 위치가 아니라 **이름으로 컬럼을 찾는다.**
머리글 행도 몇 번째인지 모르므로 위에서부터 훑어 찾는다. 표기 흔들림(0.3 / 30% / 30)도
흡수한다. 읽지 못한 것은 버리지 않고 `warnings` 로 올린다 — 조용히 틀린 수치를 내는 것보다
"이 부분은 못 읽었다" 고 말하는 편이 감독에 쓸모 있다.

계획선은 파일의 「계획」 열을 믿지 않고 **다시 계산한다.** 자기신고 값이라 기간과 어긋날 수
있고, 그 어긋남 자체가 봐야 할 신호다. 파일 값은 `declared_planned` 로 따로 남긴다.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import load_workbook

# 컬럼 이름 후보. 앞에 있을수록 우선한다. 소문자·공백제거 후 부분일치로 본다.
_COLUMNS: dict[str, tuple[str, ...]] = {
    "wbs_id": ("wbsid", "wbs", "id", "번호", "코드"),
    "name": ("업무분류", "작업명", "업무명", "활동명", "업무", "작업", "활동", "task", "activity"),
    "deliverable": ("산출물", "결과물", "deliverable", "output"),
    "start": ("시작일", "착수일", "시작", "start"),
    "end": ("종료일", "완료일", "마감일", "종료", "end", "finish", "due"),
    "weight": ("가중치", "비중", "weight"),
    "planned": ("계획", "계획율", "계획진척", "plan"),
    "actual": ("실적", "실적율", "진척률", "진척율", "달성률", "actual", "progress"),
}

# 머리글을 찾을 때 훑는 최대 행 수. 표지·기준일 안내가 위에 붙는 양식이 많다.
_HEADER_SCAN_ROWS = 20

# 진척으로 인정할 최소 컬럼. 이게 없으면 산정 자체가 성립하지 않는다.
_REQUIRED = ("weight", "actual")


@dataclass
class WbsRow:
    wbs_id: str
    name: str
    deliverable: str | None
    start: date | None
    end: date | None
    weight: float
    actual: float
    declared_planned: float | None

    def planned_at(self, at: date) -> float:
        """기간 안분. 시작 전 0, 종료 후 1, 사이는 경과 비율."""
        if self.start is None or self.end is None:
            return 0.0
        if at <= self.start:
            return 0.0
        if at >= self.end:
            return 1.0
        span = (self.end - self.start).days
        return 0.0 if span <= 0 else (at - self.start).days / span


@dataclass
class WbsGroup:
    """가중치가 없는 상위 항목. 진척 계산에는 안 들어가고 일정 화면의 묶음으로만 쓴다."""

    wbs_id: str
    name: str
    start: date | None
    end: date | None


@dataclass
class WbsPlan:
    rows: list[WbsRow]
    weight_total: float
    warnings: list[str] = field(default_factory=list)
    groups: list[WbsGroup] = field(default_factory=list)

    @property
    def leaf_count(self) -> int:
        return len(self.rows)


@dataclass
class WbsProgress:
    actual: float
    planned: float
    declared_planned: float | None
    leaf_count: int
    weight_total: float
    behind: list[str]
    warnings: list[str]

    @property
    def deviation(self) -> float:
        """실적 − 계획. 음수면 계획보다 뒤처져 있다."""
        return round(self.actual - self.planned, 4)


class WbsParseError(Exception):
    """WBS 로 읽을 수 없는 파일. 호출부가 사용자 오류로 옮긴다."""


def parse(data: bytes) -> WbsPlan:
    """xlsx 바이트를 WBS 로 읽는다. 말단 작업만 담는다."""
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:  # openpyxl 은 포맷별로 다른 예외를 던진다
        raise WbsParseError(f"엑셀 파일로 열 수 없습니다: {exc}") from exc

    try:
        grid = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()

    header_row, columns = _find_header(grid)
    if header_row is None:
        raise WbsParseError(
            "머리글을 찾지 못했습니다. 가중치·실적 열이 있는 표가 필요합니다 "
            f"(위에서 {_HEADER_SCAN_ROWS}행까지 확인했습니다)"
        )

    warnings: list[str] = []
    for key in ("wbs_id", "start", "end"):
        if key not in columns:
            warnings.append(f"「{_COLUMNS[key][0]}」 열이 없습니다")

    rows: list[WbsRow] = []
    groups: list[WbsGroup] = []
    for index, raw in enumerate(grid[header_row + 1 :], start=header_row + 2):
        row = _read_row(raw, columns, index, warnings)
        if row is not None:
            rows.append(row)
            continue
        group = _read_group(raw, columns)
        if group is not None:
            groups.append(group)

    if not rows:
        raise WbsParseError("가중치가 있는 말단 작업을 한 건도 찾지 못했습니다")

    total = round(sum(r.weight for r in rows), 6)
    if abs(total - 1.0) > 0.005:
        warnings.append(f"가중치 합이 1.00 이 아닙니다({total:.3f}). 합으로 나눠 맞췄습니다")

    return WbsPlan(rows=rows, weight_total=total, warnings=warnings, groups=groups)


def progress(plan: WbsPlan, at: date | None = None) -> WbsProgress:
    """가중 진척률과 계획선. 가중치 합으로 나누므로 합이 1이 아니어도 성립한다."""
    at = at or date.today()
    total = plan.weight_total or 1.0

    actual = sum(r.weight * r.actual for r in plan.rows) / total
    planned = sum(r.weight * r.planned_at(at) for r in plan.rows) / total

    declared = [r for r in plan.rows if r.declared_planned is not None]
    declared_planned = (
        sum(r.weight * (r.declared_planned or 0.0) for r in declared) / total
        if len(declared) == len(plan.rows)
        else None
    )

    # 계획보다 뒤처진 말단. 반올림 오차로 걸리지 않게 1%p 여유를 둔다.
    behind = [
        f"{r.wbs_id} {r.name}".strip()
        for r in plan.rows
        if r.actual + 0.01 < r.planned_at(at)
    ]

    return WbsProgress(
        actual=round(actual, 4),
        planned=round(planned, 4),
        declared_planned=None if declared_planned is None else round(declared_planned, 4),
        leaf_count=plan.leaf_count,
        weight_total=plan.weight_total,
        behind=behind,
        warnings=plan.warnings,
    )


# --- 읽기 세부 ------------------------------------------------------------


def _find_header(grid: list[list]) -> tuple[int | None, dict[str, int]]:
    """머리글 행과 컬럼 위치를 찾는다. 필수 열을 모두 가진 첫 행이 머리글이다."""
    for index, raw in enumerate(grid[:_HEADER_SCAN_ROWS]):
        columns = _match_columns(raw)
        if all(key in columns for key in _REQUIRED):
            return index, columns
    return None, {}


def _match_columns(raw: list) -> dict[str, int]:
    columns: dict[str, int] = {}
    for position, cell in enumerate(raw):
        text = _norm(cell)
        if not text:
            continue
        for key, candidates in _COLUMNS.items():
            if key in columns:
                continue
            if any(c in text for c in candidates):
                columns[key] = position
                break
    return columns


def _norm(cell) -> str:
    return "" if cell is None else str(cell).strip().lower().replace(" ", "")


def _read_row(
    raw: list, columns: dict[str, int], line: int, warnings: list[str]
) -> WbsRow | None:
    """가중치가 있는 행만 말단으로 본다. 상위 항목은 말단의 합이라 따로 세지 않는다."""
    weight = _number(_cell(raw, columns.get("weight")))
    if weight is None or weight <= 0:
        return None

    actual = _ratio(_cell(raw, columns.get("actual")))
    if actual is None:
        warnings.append(f"{line}행: 실적을 숫자로 읽지 못해 0 으로 계산했습니다")
        actual = 0.0

    start = _date(_cell(raw, columns.get("start")))
    end = _date(_cell(raw, columns.get("end")))
    if start and end and end < start:
        warnings.append(f"{line}행: 종료일이 시작일보다 빠릅니다")
        start, end = None, None

    return WbsRow(
        wbs_id=str(_cell(raw, columns.get("wbs_id")) or "").strip(),
        name=str(_cell(raw, columns.get("name")) or "").strip(),
        deliverable=(str(_cell(raw, columns.get("deliverable")) or "").strip() or None),
        start=start,
        end=end,
        weight=weight,
        actual=actual,
        declared_planned=_ratio(_cell(raw, columns.get("planned"))),
    )


def _read_group(raw: list, columns: dict[str, int]) -> WbsGroup | None:
    """가중치 없는 행 가운데 번호와 이름이 있는 것. 표지·빈 줄·합계 줄은 걸러진다."""
    wbs_id = str(_cell(raw, columns.get("wbs_id")) or "").strip()
    name = str(_cell(raw, columns.get("name")) or "").strip()
    if not wbs_id or not name:
        return None
    start = _date(_cell(raw, columns.get("start")))
    end = _date(_cell(raw, columns.get("end")))
    if start and end and end < start:
        start, end = None, None
    return WbsGroup(wbs_id=wbs_id, name=name, start=start, end=end)


def _cell(raw: list, position: int | None):
    if position is None or position >= len(raw):
        return None
    return raw[position]


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return None if math.isnan(value) else float(value)
    text = str(value).strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def _ratio(value) -> float | None:
    """0~1 로 맞춘다. 30 · 30% · 0.3 이 모두 0.3 이다.

    1 을 넘으면 백분율로 본다. 진척률이 100% 를 넘는 WBS 는 없으므로 안전한 가정이다.
    """
    number = _number(value)
    if number is None:
        return None
    percent = number > 1.0 or (isinstance(value, str) and value.strip().endswith("%"))
    return min(max(number / 100.0 if percent else number, 0.0), 1.0)


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
