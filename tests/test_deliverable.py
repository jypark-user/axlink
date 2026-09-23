"""WBS 산출물 제출 판정 (ARC-016 2단계). 규칙 세 개와 미제출·지연 갈림을 모델 없이 본다."""

from datetime import date

from app.dashboard import deliverable as d

TODAY = date(2026, 9, 22)
TREE = d.RepoTree(
    sha="abc123",
    paths=frozenset({
        "docs/10-requirements/IM-001-요구사항정의서.md",
        "app/integration/port.py",
    }),
    blob_url_base="https://github.com/o/r/blob/abc123/",
)
PRODUCTS = [
    {"id": "p1", "type": "PROJECT_PLAN", "title": "WBS", "status": "SUBMITTED",
     "file_uri": "docs/00-management/WBS.xlsx", "external_url": "https://github.com/o/r/blob/x/WBS.xlsx"},
    {"id": "p2", "type": "SOFTWARE_DESIGN", "title": "설계서", "status": "NONE",
     "file_uri": None, "external_url": None},
]
DOCUMENTS = [{"id": "d1", "original_filename": "중간보고서.hwp"}]


def _item(wbs_id, deliverable, end=None, weight=0.1):
    return {"wbs_id": wbs_id, "deliverable": deliverable, "end_on": end, "weight": weight}


def _one(item):
    return d.judge([item], tree=TREE, products=PRODUCTS, documents=DOCUMENTS, today=TODAY)[0]


def test_저장소_경로가_트리에_있으면_제출이고_링크가_붙는다():
    j = _one(_item("2.1", "docs/10-requirements/IM-001-요구사항정의서.md"))
    assert j.status == d.SUBMITTED and j.rule == d.RULE_PATH
    assert j.url == "https://github.com/o/r/blob/abc123/docs/10-requirements/IM-001-요구사항정의서.md"


def test_경로_대소문자와_구분자는_흔들려도_맞춘다():
    j = _one(_item("3.1", ".\\App\\Integration\\PORT.py"))
    assert j.status == d.SUBMITTED and j.ref == "app/integration/port.py"


def test_항목에_붙은_문서가_있으면_이름과_상관없이_제출이다():
    item = {**_item("1.4", "docs/50-report/중간보고서.md", end=date(2026, 1, 1)), "id": "item-1"}
    docs = [{"id": "d9", "original_filename": "아무이름.hwp", "wbs_item_id": "item-1"}]
    j = d.judge([item], tree=None, products=[], documents=docs, today=TODAY)[0]
    assert j.status == d.SUBMITTED and j.rule == d.RULE_LINK
    assert j.ref == "아무이름.hwp" and j.url == "/api/documents/d9/content"
    # 다른 항목에 붙은 문서는 이 항목의 근거가 아니다
    other = [{"id": "d8", "original_filename": "x.hwp", "wbs_item_id": "item-2"}]
    j2 = d.judge([item], tree=None, products=[], documents=other, today=TODAY)[0]
    assert j2.status == d.OVERDUE


def test_폴더를_적으면_그_아래_파일이_있을_때_제출이다():
    tree = d.RepoTree(
        sha="s", blob_url_base="https://github.com/o/r/blob/s/",
        paths=frozenset({"frontend/src/features/dashboard/page.tsx",
                         "frontend/src/features/dashboard/widgets.tsx"}),
    )
    j = d.judge([_item("6.1", "frontend/src/features/dashboard")],
                tree=tree, products=[], documents=[], today=TODAY)[0]
    assert j.status == d.SUBMITTED and j.rule == d.RULE_PATH
    assert j.ref == "frontend/src/features/dashboard/ (2개 파일)"
    assert j.url.endswith("/frontend/src/features/dashboard/page.tsx")
    # 이름만 겹치는 다른 폴더는 안 된다
    assert d.judge([_item("6.9", "frontend/src/features/dash")],
                   tree=tree, products=[], documents=[], today=TODAY)[0].status == d.MISSING


def test_수집된_산출물_경로로도_맞춘다():
    j = d.judge([_item("1.3", "docs/00-management/WBS.xlsx")],
                tree=None, products=PRODUCTS, documents=[], today=TODAY)[0]
    assert j.status == d.SUBMITTED and j.rule == d.RULE_PATH
    assert j.url == "https://github.com/o/r/blob/x/WBS.xlsx"


def test_파일_이름이_올린_문서와_같으면_제출이다():
    j = _one(_item("1.4", "docs/50-report/중간보고서.md"))  # 확장자는 달라도 이름이 같다
    assert j.status == d.SUBMITTED and j.rule == d.RULE_NAME
    assert j.ref == "중간보고서.hwp" and j.url == "/api/documents/d1/content"


def test_산출물_유형_이름이면_그_유형의_현행_산출물을_본다():
    assert _one(_item("1.2", "사업수행계획서")).rule == d.RULE_TYPE
    # 상태 NONE 인 유형은 제출이 아니다
    j = _one(_item("2.5", "설계서", end=date(2026, 11, 13)))
    assert j.status == d.MISSING


def test_없으면_미제출이고_종료일이_지났으면_지연이다():
    assert _one(_item("2.6", "docs/traceability.csv", end=date(2026, 11, 13))).status == d.MISSING
    assert _one(_item("2.6", "docs/traceability.csv", end=date(2026, 9, 1))).status == d.OVERDUE
    # 오늘이 종료일이면 아직 지연이 아니다
    assert _one(_item("2.6", "docs/traceability.csv", end=TODAY)).status == d.MISSING


def test_묶음이나_산출물_열이_비면_판정하지_않는다():
    assert _one(_item("1", "", weight=None)).status == d.NONE
    assert _one(_item("9.9", "   ")).status == d.NONE


def test_요약은_네_상태를_다_센다():
    js = d.judge(
        [_item("1", "", weight=None), _item("a", "app/integration/port.py"),
         _item("b", "x.md", end=date(2026, 1, 1)), _item("c", "y.md")],
        tree=TREE, products=[], documents=[], today=TODAY,
    )
    assert d.summarize(js) == {d.SUBMITTED: 1, d.MISSING: 1, d.OVERDUE: 1, d.NONE: 1}
