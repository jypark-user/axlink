"""질문에 적힌 기간을 집계 필터로 (GH-123, QUR.RAG.002).

"이번 달 진척 추세" 를 물으면 그 달만 집계해야 한다. 예전에는 기간이 필터로 들어가지 않아
그림이 수집 첫날부터 그려지고, 답 문장의 기간과 그림의 기간이 어긋났다.

모델에게 기간을 고르게 하지 않는다. 질문 글자에서 정해진 표현만 읽는다. 표현이 없거나 지표가
그 필터를 허용하지 않으면 필터를 붙이지 않는다(지금까지와 같다). 기준일은 사업 시간대의 오늘이다.

"이번 주"·"지난 주" 는 읽지 않는다. 주의 시작 요일을 정한 적이 없고, 지금 필터(최근 N일)로는
달력 주를 정확히 자를 수 없다.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.common import clock
from app.semantic.catalog import MeasureDef
from app.semantic.models import WidgetFilter

_THIS_MONTH = re.compile(r"이번\s*달|금월|당월")
_LAST_MONTH = re.compile(r"지난\s*달|전월|저번\s*달")
_LAST_DAYS = re.compile(r"최근\s*(\d{1,3})\s*일")
_LAST_WEEKS = re.compile(r"최근\s*(\d{1,2})\s*주")
_TODAY = re.compile(r"오늘")


def _previous_month(today: date) -> str:
    first = today.replace(day=1)
    year, month = (first.year - 1, 12) if first.month == 1 else (first.year, first.month - 1)
    return f"{year:04d}-{month:02d}"


def filter_for(
    question: str, measure: MeasureDef, today: date | None = None
) -> WidgetFilter | None:
    """질문의 기간 표현 하나를 필터로. 둘 이상이면 앞에 나온 것을 쓴다."""
    allowed = set(measure.allowed_filters)
    today = today or clock.today()
    candidates: list[tuple[int, WidgetFilter]] = []

    def add(match: re.Match | None, key: str, value: object) -> None:
        if match and key in allowed:
            field, op = key.split("__")
            found = WidgetFilter(field=field, op=op.upper(), value=value)
            candidates.append((match.start(), found))

    add(_THIS_MONTH.search(question), "period__in_month", "current")
    add(_LAST_MONTH.search(question), "period__in_month", _previous_month(today))
    m = _LAST_DAYS.search(question)
    if m and int(m.group(1)) >= 1:
        add(m, "period__last_n_days", int(m.group(1)))
    m = _LAST_WEEKS.search(question)
    if m and int(m.group(1)) >= 1:
        add(m, "period__last_n_days", int(m.group(1)) * 7)
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[0])[1]


@dataclass(frozen=True)
class ActivityRange:
    """목록 질문의 활동 기간. 양 끝 날짜를 포함한다(사업 시간대 날짜)."""

    start: date
    end: date

    @property
    def label(self) -> str:
        if self.start == self.end:
            return self.start.isoformat()
        return f"{self.start.isoformat()}~{self.end.isoformat()}"


def activity_range(question: str, today: date | None = None) -> ActivityRange | None:
    """「최근 5일 이내 작업된 요구사항」 같은 목록 질문의 기간. 집계 필터와 같은 표현만 읽는다.

    최근 N일은 집계 필터(period__last_n_days)와 같게 오늘에서 N일 전부터 오늘까지다. 같은 질문에
    집계와 목록이 다른 기간을 쓰면 안 된다. 표현이 없으면 None(기간 조건 없음).
    """
    today = today or clock.today()
    candidates: list[tuple[int, ActivityRange]] = []
    m = _THIS_MONTH.search(question)
    if m:
        candidates.append((m.start(), ActivityRange(today.replace(day=1), today)))
    m = _LAST_MONTH.search(question)
    if m:
        last_day = today.replace(day=1) - timedelta(days=1)
        candidates.append((m.start(), ActivityRange(last_day.replace(day=1), last_day)))
    m = _LAST_DAYS.search(question)
    if m and int(m.group(1)) >= 1:
        start = today - timedelta(days=int(m.group(1)))
        candidates.append((m.start(), ActivityRange(start, today)))
    m = _LAST_WEEKS.search(question)
    if m and int(m.group(1)) >= 1:
        days = int(m.group(1)) * 7
        candidates.append((m.start(), ActivityRange(today - timedelta(days=days), today)))
    m = _TODAY.search(question)
    if m:
        candidates.append((m.start(), ActivityRange(today, today)))
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[0])[1]
