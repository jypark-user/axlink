"""WBS 산출물 제출 판정 (ARC-016 2단계). 모델 없이 판정만 본다.

11-19 사용자 결정: 판정은 예상 산출물(WBS 산출물 열에서 저절로 만든 항목 + 발주기관 요청)이
모두 올라왔는가다. 예상 산출물이 없는 작업은 판정하지 않는다.
"""

from datetime import date

from app.dashboard import deliverable as d
from app.dashboard.designation import Coverage

TODAY = date(2026, 9, 22)


def _item(wbs_id, end=None, weight=0.1, key="k"):
    return {"wbs_id": wbs_id, "end_on": end, "weight": weight, "task_key": key}


def _one(item, cover=None):
    designated = {"k": cover} if cover is not None else {}
    return d.judge([item], today=TODAY, designated=designated)[0]


def test_예상_산출물이_모두_올라오면_제출이다():
    j = _one(_item("1.1"), Coverage(2, 2))
    assert (j.status, j.rule) == (d.SUBMITTED, d.RULE_DESIGNATED)
    assert j.ref == "예상 산출물 2건 중 2건 제출"


def test_덜_올라왔으면_미제출이고_종료일이_지났으면_지연이다():
    assert _one(_item("2.6", end=date(2026, 11, 13)), Coverage(2, 1)).status == d.MISSING
    assert _one(_item("2.6", end=date(2026, 9, 1)), Coverage(2, 1)).status == d.OVERDUE
    # 오늘이 종료일이면 아직 지연이 아니다
    assert _one(_item("2.6", end=TODAY), Coverage(1, 0)).status == d.MISSING


def test_예상_산출물이_없거나_묶음이면_판정하지_않는다():
    assert _one(_item("9.9")).status == d.NONE
    assert _one(_item("9.9"), Coverage(0, 0)).status == d.NONE
    assert _one(_item("1", weight=None), Coverage(1, 1)).status == d.NONE


def test_요약은_네_상태를_다_센다():
    items = [_item("1", weight=None), _item("a", key="a"),
             _item("b", end=date(2026, 1, 1), key="b"), _item("c", key="c")]
    cover = {"a": Coverage(1, 1), "b": Coverage(1, 0), "c": Coverage(1, 0)}
    js = d.judge(items, today=TODAY, designated=cover)
    assert d.summarize(js) == {d.SUBMITTED: 1, d.MISSING: 1, d.OVERDUE: 1, d.NONE: 1}
