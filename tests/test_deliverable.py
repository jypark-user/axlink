"""WBS 산출물 제출 판정 (ARC-016 2단계). 모델 없이 판정만 본다.

11-19 사용자 결정: 그 작업에 올라온 산출물(직접 올렸거나 저장소 파일을 골라 올린 것)만 제출이다.
저장소에 이름이 맞는 파일이 있거나 이름이 같은 문서가 다른 곳에 있다고 제출로 보지 않는다.
"""

from datetime import date

from app.dashboard import deliverable as d

TODAY = date(2026, 9, 22)


def _item(wbs_id, deliverable, end=None, weight=0.1, item_id=None):
    return {"wbs_id": wbs_id, "deliverable": deliverable, "end_on": end, "weight": weight,
            "id": item_id}


def _one(item, documents=()):
    return d.judge([item], documents=list(documents), today=TODAY)[0]


def test_항목에_올라온_문서가_있으면_이름과_상관없이_제출이다():
    item = _item("1.4", "docs/50-report/중간보고서.md", end=date(2026, 1, 1), item_id="item-1")
    docs = [{"id": "d9", "original_filename": "아무이름.hwp", "wbs_item_id": "item-1"}]
    j = _one(item, docs)
    assert j.status == d.SUBMITTED and j.rule == d.RULE_LINK
    assert j.ref == "아무이름.hwp" and j.url == "/api/documents/d9/content"
    # 다른 항목에 붙은 문서는 이 항목의 근거가 아니다
    other = [{"id": "d8", "original_filename": "x.hwp", "wbs_item_id": "item-2"}]
    assert _one(item, other).status == d.OVERDUE


def test_이름이_같은_문서가_다른_곳에_있어도_제출이_아니다():
    docs = [{"id": "d1", "original_filename": "중간보고서.hwp", "wbs_item_id": None}]
    j = _one(_item("1.4", "중간보고서", end=date(2026, 11, 13), item_id="i"), docs)
    assert j.status == d.MISSING and j.rule is None


def test_없으면_미제출이고_종료일이_지났으면_지연이다():
    assert _one(_item("2.6", "docs/traceability.csv", end=date(2026, 11, 13))).status == d.MISSING
    assert _one(_item("2.6", "docs/traceability.csv", end=date(2026, 9, 1))).status == d.OVERDUE
    # 오늘이 종료일이면 아직 지연이 아니다
    assert _one(_item("2.6", "docs/traceability.csv", end=TODAY)).status == d.MISSING


def test_묶음이나_산출물_열이_비면_판정하지_않는다():
    assert _one(_item("1", "", weight=None)).status == d.NONE
    assert _one(_item("9.9", "   ")).status == d.NONE


def test_요약은_네_상태를_다_센다():
    docs = [{"id": "x", "original_filename": "port.py", "wbs_item_id": "a"}]
    js = d.judge(
        [_item("1", "", weight=None), _item("a", "app/integration/port.py", item_id="a"),
         _item("b", "x.md", end=date(2026, 1, 1)), _item("c", "y.md")],
        documents=docs, today=TODAY,
    )
    assert d.summarize(js) == {d.SUBMITTED: 1, d.MISSING: 1, d.OVERDUE: 1, d.NONE: 1}
