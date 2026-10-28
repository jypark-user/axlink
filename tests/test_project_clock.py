"""사업 기준일 (점검 TIME-01). "오늘" 은 서버 시간대가 아니라 Asia/Seoul 날짜다.
화면·직접 조회의 기본 기준일과 스케줄러의 일별 스냅샷 날짜가 같은 날을 본다.
"""

import pathlib
import re
from datetime import UTC, date, datetime

import pytest

from app import scheduler
from app.common import clock

# 한국 10-27 00:30 = UTC 10-26 15:30. 서버가 UTC 면 date.today() 는 10-26 을 낸다
KST_AFTER_MIDNIGHT = datetime(2026, 10, 26, 15, 30, tzinfo=UTC)


@pytest.mark.parametrize(("at", "expected"), [
    (datetime(2026, 10, 26, 14, 59, tzinfo=UTC), date(2026, 10, 26)),  # 한국 23:59
    (datetime(2026, 10, 26, 15, 0, tzinfo=UTC), date(2026, 10, 27)),   # 한국 00:00
    (datetime(2026, 10, 27, 0, 0, tzinfo=UTC), date(2026, 10, 27)),    # 한국 09:00
])
def test_오늘은_한국_날짜다(at, expected):
    assert clock.today(at) == expected


def test_스케줄러와_화면이_같은_날을_본다(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: KST_AFTER_MIDNIGHT)
    assert clock.today() == KST_AFTER_MIDNIGHT.astimezone(scheduler.LOCAL_TZ).date()
    assert clock.today() == date(2026, 10, 27)


def test_서버_시간대에_기대는_오늘_계산이_남아_있지_않다():
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    found = [
        f"{p.relative_to(root)}:{n}"
        for p in root.rglob("*.py") if p.name != "clock.py"
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"\bdate\.today\(\)|datetime\.now\(\)|\bcurrent_date\b", line)
    ]
    assert found == []
