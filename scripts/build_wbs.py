#!/usr/bin/env python3
"""docs/00-management/WBS.xlsx 생성기.

WBS 는 진척의 기준이다(SWFR.PIP.010). 그런데 xlsx 는 바이너리라 커밋 diff 로
무엇이 바뀌었는지 볼 수 없다 — 이 저장소는 커밋 자체가 진척 데이터인데
정작 기준선의 변경 이력이 안 보이면 곤란하다. 그래서 데이터를 여기 두고 생성한다.

컬럼은 발주기관 참고자료 PM-002 구조를 그대로 쓴다.
    WBS ID · 업무분류 · 산출물 · 시작일 · 종료일 · 가중치 · 계획 · 실적

    .venv/Scripts/python scripts/build_wbs.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "00-management" / "WBS.xlsx"

PROJECT = "2026년 AX 프로젝트 관리 운영 프레임워크 개발 용역 (AX Link)"
BASE_DATE = date(2026, 9, 3)  # 기준일 — 계획선을 이 날짜로 계산한다

HEADERS = ["WBS ID", "업무분류", "산출물", "시작일", "종료일", "가중치", "계획", "실적"]

# (WBS ID, 업무분류, 산출물, 시작, 종료, 가중치, 실적)
# 가중치·실적은 말단에만 둔다. 상위 항목은 파서가 말단을 합산한다.
# 실적은 2026-09-03 현재 실제 상태다. 신고와 산출물 관측이 어긋나면 시스템이 짚어낸다.
ROWS: list[tuple] = [
    ("1", "사업관리", "", "2026-08-11", "2026-11-30", None, None),
    ("1.1", "착수보고", "docs/00-management/작업계획.md", "2026-08-11", "2026-08-11", 0.01, 1.00),
    ("1.2", "범위·평가기준 합의", "docs/00-management/M1-합의서(안).docx", "2026-08-24", "2026-08-29", 0.02, 1.00),
    ("1.3", "진척 기준선 수립·유지", "docs/00-management/WBS.xlsx", "2026-09-01", "2026-11-30", 0.02, 0.30),
    ("1.4", "중간보고", "docs/50-report/중간보고서.md", "2026-09-22", "2026-09-30", 0.01, 0.00),
    ("1.5", "최종보고", "docs/50-report/최종결과보고서.md", "2026-11-02", "2026-11-13", 0.02, 0.00),

    ("2", "요구사항·설계", "", "2026-08-24", "2026-11-13", None, None),
    ("2.1", "요구사항정의서", "docs/10-requirements/IM-001-요구사항정의서.md", "2026-08-24", "2026-08-28", 0.04, 1.00),
    ("2.2", "E2E 사용자 시나리오", "docs/10-requirements/E2E-사용자시나리오.md", "2026-08-24", "2026-08-28", 0.02, 1.00),
    ("2.3", "백엔드 언어 전환 결정", "docs/20-design/ARC-001-백엔드-언어-파이썬-전환.md", "2026-08-27", "2026-08-28", 0.02, 1.00),
    ("2.4", "진척률 산정체계 설계", "docs/20-design/진척률-산정체계.md", "2026-08-25", "2026-08-29", 0.02, 1.00),
    ("2.5", "SW 설계서", "docs/20-design/IM-003-SW설계서.md", "2026-10-26", "2026-11-13", 0.02, 0.00),
    ("2.6", "요구사항 추적표", "docs/traceability.csv", "2026-09-14", "2026-11-13", 0.01, 0.10),

    ("3", "연계·수집", "", "2026-08-28", "2026-09-11", None, None),
    ("3.1", "커넥터 포트·어댑터 구조", "app/integration/port.py", "2026-09-03", "2026-09-05", 0.03, 0.00),
    ("3.2", "GitHub 커넥터", "app/integration/github.py", "2026-08-28", "2026-08-28", 0.03, 1.00),
    ("3.3", "Redmine 커넥터", "app/integration/redmine.py", "2026-09-08", "2026-09-11", 0.04, 0.00),
    ("3.4", "증분 수집 워터마크", "app/integration/sync.py", "2026-09-08", "2026-09-11", 0.03, 0.00),
    ("3.5", "문서 추출 (PDF·DOCX·XLSX·HWP)", "app/document/extractor.py", "2026-08-28", "2026-09-02", 0.03, 1.00),
    ("3.6", "문서 업로드·보관", "app/document/service.py", "2026-09-02", "2026-09-02", 0.02, 1.00),

    ("4", "표준화·집계", "", "2026-08-31", "2026-09-30", None, None),
    ("4.1", "표준 데이터 모델 적재", "app/standard/mapping.py", "2026-08-31", "2026-08-31", 0.04, 1.00),
    ("4.2", "추적관계 생성", "app/standard/trace.py", "2026-09-14", "2026-09-18", 0.04, 0.00),
    ("4.3", "WBS 파싱·진척 산정", "app/dashboard/wbs.py", "2026-09-14", "2026-09-25", 0.07, 0.00),
    ("4.4", "산출물 대조", "app/dashboard/deliverable.py", "2026-09-21", "2026-09-25", 0.03, 0.00),
    ("4.5", "일별 스냅샷·추이", "app/dashboard/snapshot.py", "2026-09-28", "2026-09-30", 0.03, 0.00),
    ("4.6", "지표 산출 (일정·품질·산출물)", "app/dashboard/metric.py", "2026-09-21", "2026-09-30", 0.03, 0.00),

    ("5", "AI·RAG", "", "2026-08-31", "2026-10-23", None, None),
    ("5.1", "임베딩 포트·청킹·색인", "app/rag/indexing.py", "2026-08-31", "2026-09-02", 0.04, 1.00),
    ("5.2", "하이브리드 검색", "app/rag/search.py", "2026-10-01", "2026-10-08", 0.04, 0.00),
    ("5.3", "근거 게이트·출처 응답", "app/ai/answer.py", "2026-10-09", "2026-10-16", 0.04, 0.00),
    ("5.4", "온프레미스 LLM 전환", "docs/20-design/인프라-배치방안.md", "2026-10-19", "2026-10-23", 0.02, 0.00),
    ("5.5", "폐쇄망 구동 검증", "docs/30-test/폐쇄망-검증결과.md", "2026-10-12", "2026-10-16", 0.03, 0.00),

    ("6", "워크스페이스", "", "2026-09-14", "2026-10-23", None, None),
    ("6.1", "대시보드·위젯", "frontend/src/features/dashboard", "2026-09-21", "2026-09-30", 0.04, 0.00),
    ("6.2", "확인 요청·조치 보고", "frontend/src/features/changes", "2026-09-28", "2026-10-09", 0.03, 0.00),
    ("6.3", "추적성 화면", "frontend/src/features/traceability", "2026-09-14", "2026-09-18", 0.02, 0.00),
    ("6.4", "E2E 관리순환 시연 구성", "docs/30-test/E2E-시연-시나리오.md", "2026-10-19", "2026-10-23", 0.01, 0.00),

    ("7", "시험·인도", "", "2026-10-26", "2026-11-30", None, None),
    ("7.1", "시험 케이스 작성·수행", "docs/30-test/IM-005-시험계획및결과서.md", "2026-10-26", "2026-11-06", 0.03, 0.00),
    ("7.2", "결함 조치", "docs/30-test/IM-006-결함관리대장.md", "2026-11-02", "2026-11-13", 0.02, 0.00),
    ("7.3", "사용자 매뉴얼", "docs/40-manual/IM-007-사용자매뉴얼.md", "2026-11-02", "2026-11-13", 0.03, 0.00),
    ("7.4", "산출물 일체 인도", "docs/50-report/인도목록.md", "2026-11-16", "2026-11-30", 0.02, 0.00),
]


def planned(start: date, end: date, at: date) -> float:
    """계획선 — 기간 안분. 진척률-산정체계 §2.2 의 clamp((t−시작)/(종료−시작), 0, 1)."""
    if at <= start:
        return 0.0
    if at >= end:
        return 1.0
    span = (end - start).days
    return 0.0 if span <= 0 else round((at - start).days / span, 2)


def build() -> tuple[int, float]:
    wb = Workbook()
    ws = wb.active
    ws.title = "WBS"

    thin = Side(style="thin", color="C9D2DC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws["A1"] = PROJECT
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"기준일 {BASE_DATE:%Y-%m-%d} · 가중치 합 1.00 · 계획은 기간 안분값"
    ws["A2"].font = Font(size=10, color="616D7E")

    head_row = 4
    for col, name in enumerate(HEADERS, start=1):
        cell = ws.cell(row=head_row, column=col, value=name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F6DB0")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    leaves = 0
    total_weight = 0.0
    for offset, (wbs_id, name, product, start, end, weight, actual) in enumerate(ROWS):
        r = head_row + 1 + offset
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        is_leaf = weight is not None
        if is_leaf:
            leaves += 1
            total_weight += weight

        ws.cell(row=r, column=1, value=wbs_id)
        # 계층은 들여쓰기로도 보이게 한다 — 사람이 여는 파일이기도 하다.
        ws.cell(row=r, column=2, value=("    " * wbs_id.count(".")) + name)
        ws.cell(row=r, column=3, value=product or None)
        ws.cell(row=r, column=4, value=s).number_format = "yyyy-mm-dd"
        ws.cell(row=r, column=5, value=e).number_format = "yyyy-mm-dd"
        ws.cell(row=r, column=6, value=weight).number_format = "0.00"
        ws.cell(row=r, column=7, value=planned(s, e, BASE_DATE) if is_leaf else None)
        ws.cell(row=r, column=8, value=actual)
        ws.cell(row=r, column=7).number_format = "0%"
        ws.cell(row=r, column=8).number_format = "0%"

        for col in range(1, len(HEADERS) + 1):
            cell = ws.cell(row=r, column=col)
            cell.border = border
            if not is_leaf:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="EEF1F5")

    for col, width in enumerate((10, 34, 46, 13, 13, 9, 9, 9), start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    return leaves, total_weight


def main() -> int:
    leaves, total = build()
    print(f"{OUT.relative_to(ROOT)} — 전체 {len(ROWS)}행 · 말단 {leaves}개 · 가중치 합 {total:.2f}")
    if abs(total - 1.0) > 0.005:
        print(f"  가중치 합이 1.00 이 아니다: {total:.3f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
