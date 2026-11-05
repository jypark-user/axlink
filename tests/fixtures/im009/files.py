"""IM-009 공통 시험 자료의 가상 파일을 만든다 (docs/30-test/IM-009-공통시험자료.md 4.2·4.4·5.1·5.2).

여기서 만드는 것은 DOCX·XLSX·MD 다. PDF(TD-DOC-4·7·11·16)·HWP(TD-DOC-12·15)·HWPX(TD-DOC-13)·
손상 파일(TD-DOC-10)은 생성기가 없어 `make_all()` 이 만들지 않는다. `MISSING` 목록으로 돌려주고
투입 스크립트가 「자료 없음」으로 기록한다. 내용은 문서의 「핵심 내용·위치」 열과 같아야 한다.
값을 바꾸면 IM-009 7절 기대값이 깨진다.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from openpyxl import Workbook

# 5.1 WBS — 열 머리글과 말단 5건. 계획 열은 참고용 파일 값이다(계획선은 재계산).
WBS_HEADER = ["WBS ID", "업무분류", "산출물", "시작일", "종료일", "가중치", "계획", "실적"]
WBS_PARENT = ["3", "수행", "", "2026-03-02", "2026-11-30", "", "", ""]
WBS_LEAVES_S0 = [
    ["3.1", "요구사항 정의", "요구사항정의서", "2026-03-02", "2026-04-15", 0.15, 1.00, 1.00],
    ["3.2", "설계", "SW설계서", "2026-04-16", "2026-07-31", 0.20, 1.00, 0.40],
    ["3.3", "구현", "프로그램 목록", "2026-06-01", "2026-10-15", 0.35, 0.80, 0.20],
    ["3.4", "시험", "시험결과서", "2026-09-01", "2026-10-31", 0.20, 0.30, 0.00],
    ["3.5", "인도", "사용자매뉴얼", "2026-11-01", "2026-11-30", 0.10, 0.00, 0.00],
]


def _wbs_rows(leaves: list[list], *, drop_weight: bool = False) -> tuple[list[str], list[list]]:
    header = list(WBS_HEADER)
    parent = list(WBS_PARENT)
    rows = [list(r) for r in leaves]
    if drop_weight:
        i = header.index("가중치")
        header.pop(i)
        parent.pop(i)
        for r in rows:
            r.pop(i)
    return header, [parent, *rows]


def _xlsx(
    path: Path,
    sheet: str,
    header: list[str] | None,
    rows: list[list],
    preamble: list[list] | None = None,
) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for r in preamble or []:
        ws.append(r)
    if header:
        ws.append(header)
    for r in rows:
        ws.append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def wbs_s0(path: Path) -> Path:
    """TD-DOC-6 WBS.xlsx (S0 실적). 시트 「WBS」, 머리글 1행, 자료 2~7행."""
    header, rows = _wbs_rows(WBS_LEAVES_S0)
    return _xlsx(path, "WBS", header, rows)


def wbs_s1(path: Path) -> Path:
    """S1: 3.2 실적 40% → 85%."""
    leaves = [list(r) for r in WBS_LEAVES_S0]
    leaves[1][7] = 0.85
    header, rows = _wbs_rows(leaves)
    return _xlsx(path, "WBS", header, rows)


def wbs_l2(path: Path) -> Path:
    """TD-WBS-L2: 가중치 열 전체 삭제."""
    header, rows = _wbs_rows(WBS_LEAVES_S0, drop_weight=True)
    return _xlsx(path, "WBS", header, rows)


def wbs_miss(path: Path) -> Path:
    """TD-WBS-MISS: 3.4 산출물 칸 비움."""
    leaves = [list(r) for r in WBS_LEAVES_S0]
    leaves[3][2] = ""
    header, rows = _wbs_rows(leaves)
    return _xlsx(path, "WBS", header, rows)


def wbs_sum(path: Path) -> Path:
    """TD-WBS-SUM: 3.5 가중치 0.10 → 0.20 (합 1.10)."""
    leaves = [list(r) for r in WBS_LEAVES_S0]
    leaves[4][5] = 0.20
    header, rows = _wbs_rows(leaves)
    return _xlsx(path, "WBS", header, rows)


def wbs_nohead(path: Path) -> Path:
    """TD-WBS-NOHEAD: 1~3행 제목·설명, 머리글 없음, 가중치·실적 열 없음."""
    preamble = [["시민포털 고도화 사업수행계획"], ["작성: 다온소프트"], ["일정표"]]
    rows = [
        ["3.1", "요구사항 정의", "요구사항정의서", "2026-03-02", "2026-04-15"],
        ["3.2", "설계", "SW설계서", "2026-04-16", "2026-07-31"],
    ]
    return _xlsx(path, "WBS", None, rows, preamble=preamble)


def wbs_v2(path: Path) -> Path:
    """TD-WBS-V2: 3.4 → 3.4 시험(0.12)·3.5 인수시험(0.08), 인도 → 3.6(0.10). 말단 6, 합 1.00."""
    leaves = [
        *[list(r) for r in WBS_LEAVES_S0[:3]],
        ["3.4", "시험", "시험결과서", "2026-09-01", "2026-10-31", 0.12, 0.30, 0.00],
        ["3.5", "인수시험", "인수시험결과서", "2026-10-15", "2026-11-15", 0.08, 0.00, 0.00],
        ["3.6", "인도", "사용자매뉴얼", "2026-11-01", "2026-11-30", 0.10, 0.00, 0.00],
    ]
    header, rows = _wbs_rows(leaves)
    return _xlsx(path, "WBS", header, rows)


# 4.2 / 4.4 요구사항 명세서

SPEC_HEADER = ["요구사항 ID", "요구사항 명칭", "중요도"]
SPEC_ROWS_V1 = [
    ("UR.PORT.001", "통합 로그인", "필수"),
    ("UR.PORT.002", "민원 신청 조회·취소", "필수"),
    ("UR.PORT.004", "알림 발송", "필수"),
]


def _docx_table(doc: Document, header: list[str], rows: list[tuple]) -> None:
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    for i, h in enumerate(header):
        table.rows[0].cells[i].text = h
    for r in rows:
        cells = table.add_row().cells
        for i, v in enumerate(r):
            cells[i].text = str(v)


def spec_v1(path: Path) -> Path:
    """TD-DOC-1 요구사항명세서_v1.0.docx: 상위 절 제목 「SR.PORT.01 포털 기능」 + 표 1(3행). 1쪽."""
    doc = Document()
    doc.add_heading("요구사항 명세서 v1.0", level=1)
    doc.add_paragraph("시민포털 고도화 사업의 소프트웨어 요구사항 명세서다.")
    doc.add_heading("SR.PORT.01 포털 기능", level=2)
    _docx_table(doc, SPEC_HEADER, SPEC_ROWS_V1)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def requirements_definition(path: Path) -> Path:
    """TD-DOC-2 요구사항정의서.docx.

    표 「요구사항 목록」 3행 + 2절(2쪽) 문단 「요구사항은 총 3건이다」."""
    doc = Document()
    doc.add_heading("요구사항정의서", level=1)
    doc.add_heading("1. 요구사항 목록", level=2)
    _docx_table(
        doc,
        ["요구사항 ID", "명칭", "중요도"],
        [
            ("UR.PORT.001", "통합 로그인", "필수"),
            ("UR.PORT.002", "민원 신청 조회", "필수"),
            ("UR.PORT.003", "접속 통계", "선택"),
        ],
    )
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    doc.add_heading("2. 요약", level=2)
    doc.add_paragraph("요구사항은 총 3건이다.")
    doc.add_paragraph("필수 2건, 선택 1건으로 구성된다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def sw_design(path: Path) -> Path:
    """TD-DOC-3 SW설계서_v0.9.docx: 3.2절 문단 「외부 연계 규격은 2026-08-25 협의를 마쳤다」."""
    doc = Document()
    doc.add_heading("SW설계서 v0.9", level=1)
    doc.add_heading("1. 개요", level=2)
    doc.add_paragraph("시민포털 고도화의 소프트웨어 설계를 기술한다.")
    doc.add_heading("2. 구조 설계", level=2)
    doc.add_paragraph("포털은 인증, 민원 조회, 통계 세 모듈로 나눈다.")
    doc.add_heading("3. 인터페이스 설계", level=2)
    doc.add_heading("3.1 내부 인터페이스", level=3)
    doc.add_paragraph("모듈 사이는 REST 로 호출한다.")
    doc.add_heading("3.2 외부 연계", level=3)
    doc.add_paragraph("외부 연계 규격은 2026-08-25 협의를 마쳤다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def meeting_minutes(path: Path) -> Path:
    """TD-DOC-5 회의록_2026-08-25.docx.

    「논의 사항」 절 2번째 문단 「외부 연계 규격 협의가 지연돼 설계 완료가 늦어졌다」. 1쪽."""
    doc = Document()
    doc.add_heading("회의록 2026-08-25", level=1)
    doc.add_paragraph("참석: 가람시 정보화원 김주무관, 다온소프트 박피엠")
    doc.add_heading("논의 사항", level=2)
    doc.add_paragraph("외부 기관과 연계 규격을 확정했다.")
    doc.add_paragraph("외부 연계 규격 협의가 지연돼 설계 완료가 늦어졌다.")
    doc.add_heading("결정 사항", level=2)
    doc.add_paragraph("설계서 초안을 9월 중 제출한다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def spec_dup_ids(path: Path) -> Path:
    """TD-DOC-8 중복ID-명세서.xlsx: 4행, 2·3행 코드가 둘 다 UR.TEST.002."""
    rows = [
        ("UR.TEST.001", "첫 요구사항", "필수"),
        ("UR.TEST.002", "둘째 요구사항", "필수"),
        ("UR.TEST.002", "셋째 요구사항(코드 중복)", "선택"),
        ("UR.TEST.003", "넷째 요구사항", "선택"),
    ]
    return _xlsx(path, "명세서", SPEC_HEADER, [list(r) for r in rows])


def spec_bad_format(path: Path) -> Path:
    """TD-DOC-9 형식오류-명세서.xlsx: 1행 코드 하이픈, 2행 명칭 빈칸."""
    rows = [("UR-TEST-001", "하이픈 코드", "필수"), ("UR.TEST.002", "", "필수")]
    return _xlsx(path, "명세서", SPEC_HEADER, [list(r) for r in rows])


def risk_register(path: Path) -> Path:
    """TD-DOC-14 위험관리대장.xlsx: 1~3행 집계 블록, 4행 머리글, 5~9행 자료 5건."""
    preamble = [["위험관리대장"], ["총 5건 · 열림 2"], [""]]
    header = ["번호", "위험", "심각도", "상태", "담당"]
    rows = [
        [1, "외부 기관 일정 미확정", "높음", "열림", "박피엠"],
        [2, "서버 반입 지연", "중간", "종료", "최과장"],
        [3, "인력 교체", "낮음", "종료", "박피엠"],
        [4, "보안 점검 지연", "중간", "열림", "최과장"],
        [5, "예산 집행 지연", "낮음", "종료", "박피엠"],
    ]
    return _xlsx(path, "대장", header, rows, preamble=preamble)


DESIGN_DOC_R1 = """# 설계: 민원 조회

| 항목 | 값 |
|---|---|
| 문서 | 설계-민원조회 |
| 관련 요구사항 | UR.PORT.002 |
| 작성 | 다온소프트 |

## 1. 개요

민원 신청 조회 화면의 설계를 기술한다.

## 2. 화면 구성

조회 조건은 접수 번호와 기간이다.

결과는 접수일 내림차순으로 보인다. 취소는 접수 상태에서만 가능하다.
## 3. 범위

접속 통계 기능(UR.PORT.003 은 범위 밖)은 이 문서에서 다루지 않는다.

## 4. 데이터

조회 결과는 민원 테이블에서 읽는다.
"""


def design_doc_r1(path: Path) -> Path:
    """TD-DOC-R1 docs/20-design/설계-민원조회.md.

    머리 표 6줄에 UR.PORT.002, 20줄에 UR.PORT.003 지나가는 언급."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DESIGN_DOC_R1, encoding="utf-8")
    lines = DESIGN_DOC_R1.splitlines()
    assert "UR.PORT.002" in lines[5], "머리 표의 요구사항 코드는 6줄에 있어야 한다"
    assert "UR.PORT.003" in lines[19], "지나가는 언급은 20줄에 있어야 한다"
    return path


# 생성기가 없는 자료. 투입 때 「자료 없음」으로 기록한다.
MISSING = {
    "TD-DOC-4": "과업지시서.pdf (한글 글꼴 포함 PDF 생성기 없음)",
    "TD-DOC-7": "카드형-명세서.pdf",
    "TD-DOC-10": "손상파일.docx",
    "TD-DOC-11": "대용량.pdf",
    "TD-DOC-12": "설계검토회의록.hwp (HWP 5.0 바이너리)",
    "TD-DOC-13": "설계검토회의록.hwpx",
    "TD-DOC-15": "암호문서.hwp",
    "TD-DOC-16": "스캔문서.pdf",
}

GENERATORS = {
    "TD-DOC-1": ("요구사항명세서_v1.0.docx", spec_v1),
    "TD-DOC-2": ("요구사항정의서.docx", requirements_definition),
    "TD-DOC-3": ("SW설계서_v0.9.docx", sw_design),
    "TD-DOC-5": ("회의록_2026-08-25.docx", meeting_minutes),
    "TD-DOC-6": ("WBS.xlsx", wbs_s0),
    "TD-DOC-6-S1": ("WBS-S1.xlsx", wbs_s1),
    "TD-WBS-L2": ("WBS-L2.xlsx", wbs_l2),
    "TD-WBS-MISS": ("WBS-MISS.xlsx", wbs_miss),
    "TD-WBS-SUM": ("WBS-SUM.xlsx", wbs_sum),
    "TD-WBS-NOHEAD": ("WBS-NOHEAD.xlsx", wbs_nohead),
    "TD-WBS-V2": ("WBS-V2.xlsx", wbs_v2),
    "TD-DOC-8": ("중복ID-명세서.xlsx", spec_dup_ids),
    "TD-DOC-9": ("형식오류-명세서.xlsx", spec_bad_format),
    "TD-DOC-14": ("위험관리대장.xlsx", risk_register),
    "TD-DOC-R1": ("설계-민원조회.md", design_doc_r1),
}


def make_all(out_dir: Path) -> dict[str, Path]:
    """모든 생성 가능 자료를 out_dir 에 만든다. {자료 ID: 경로}."""
    made: dict[str, Path] = {}
    for tid, (name, fn) in GENERATORS.items():
        made[tid] = fn(out_dir / name)
    return made


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("var/verify/im009-files")
    for tid, p in make_all(target).items():
        print(tid, p)
    for tid, why in MISSING.items():
        print("없음", tid, why)
