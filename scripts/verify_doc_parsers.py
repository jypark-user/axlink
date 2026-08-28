"""문서 파서 검증 스파이크 — RSK-010 / RSK-011.

파일럿의 Java 파서(hwplib·Tika)를 파이썬으로 갈아탈 수 있는지 실측한다.
핵심 질문: hwp-hwpx-parser 가 표의 셀 구조를 보존하는가(pyhwp 가 못 하던 것).

    .venv/Scripts/python scripts/verify_doc_parsers.py

실제 HWP 5.0 공문서 샘플이 있으면 인자로 넘긴다:
    .venv/Scripts/python scripts/verify_doc_parsers.py path/to/공문서.hwp
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def band(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * 4}")


# --- 1. 최소 HWPX 를 만들어 표 추출 경로를 검증한다 -------------------------
# HWPX 는 OWPML(zip+XML). 파서는 tbl>tr>tc>p>t 를 로컬명으로 매칭한다.
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


def _p(text: str) -> str:
    return f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>'


def _tc(text: str) -> str:
    return f'<hp:tc><hp:subList>{_p(text)}</hp:subList></hp:tc>'


def _tr(cells: list[str]) -> str:
    return "<hp:tr>" + "".join(_tc(c) for c in cells) + "</hp:tr>"


def build_sample_hwpx(path: Path) -> None:
    rows = [
        ["산출물", "담당", "상태"],
        ["요구사항정의서", "PM", "승인"],
        ["SW설계서", "설계", "작성중"],
    ]
    table = "<hp:tbl>" + "".join(_tr(r) for r in rows) + "</hp:tbl>"
    section = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hs:sec xmlns:hp="{HP}" xmlns:hs="{HS}">'
        f'{_p("사업 산출물 현황")}{table}{_p("이상 끝")}'
        f'</hs:sec>'
    )
    header = f'<?xml version="1.0" encoding="UTF-8"?><hh:head xmlns:hh="{HP}"/>'
    manifest = '<?xml version="1.0" encoding="UTF-8"?><manifest/>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype 은 무압축 첫 엔트리가 관례다
        z.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/manifest.xml", manifest)
        z.writestr("Contents/header.xml", header)
        z.writestr("Contents/section0.xml", section)
    return rows


def verify_hwpx() -> bool:
    band("HWPX — 표 셀 구조 추출 (RSK-010 핵심)")
    from hwp_hwpx_parser import ExtractOptions, HWPXReader, TableStyle, extract_hwpx

    sample = ROOT / "build" / "sample.hwpx"
    sample.parent.mkdir(exist_ok=True)
    expected = build_sample_hwpx(sample)

    text, err = extract_hwpx(sample, ExtractOptions(table_style=TableStyle.MARKDOWN))
    print("추출 텍스트:")
    for line in text.splitlines():
        print("  |", line)
    if err:
        print("  경고:", err)

    tables = HWPXReader(sample).get_tables()
    ok = bool(tables) and tables[0].rows == expected
    print(f"\n표 개수: {len(tables)}")
    if tables:
        print("첫 표 rows:", tables[0].rows)
    print(f"셀 구조 원본 일치: {'예' if ok else '아니오'}")
    md_ok = "|" in text and "산출물" in text
    print(f"마크다운 표 렌더: {'예' if md_ok else '아니오'}")
    return ok and md_ok


def verify_hwp5(path: Path) -> bool:
    band(f"HWP 5.0 (실파일) — {path.name}")
    from hwp_hwpx_parser import ExtractOptions, HWP5Reader, TableStyle, extract_hwp5

    text, err = extract_hwp5(path, ExtractOptions(table_style=TableStyle.MARKDOWN))
    print(f"텍스트 길이: {len(text)}자")
    print("앞부분:", text[:200].replace("\n", " ⏎ "))
    if err:
        print("경고:", err)
    tables = HWP5Reader(path).get_tables()
    print(f"표 개수: {len(tables)}")
    if tables:
        print("첫 표 첫 행:", tables[0].rows[0] if tables[0].rows else "(비어있음)")
    return len(text) > 0


def verify_docx() -> bool:
    band("DOCX — python-docx (실파일: M1 합의서)")
    from docx import Document

    path = ROOT / "docs" / "00-management" / "M1-합의서(안).docx"
    if not path.exists():
        print("파일 없음, 건너뜀")
        return False
    doc = Document(path)
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    print(f"문단 수: {len(paras)} · 표 수: {len(doc.tables)}")
    print("첫 문단 3개:")
    for p in paras[:3]:
        print("  |", p[:70])
    if doc.tables:
        t = doc.tables[0]
        print(f"첫 표: {len(t.rows)}행 × {len(t.columns)}열")
        print("  첫 행:", [c.text for c in t.rows[0].cells])
    return len(paras) > 0


def verify_xlsx() -> bool:
    band("XLSX — openpyxl (WBS 파서용 · RSK-004 재확인)")
    from openpyxl import Workbook, load_workbook

    path = ROOT / "build" / "sample.xlsx"
    path.parent.mkdir(exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "WBS"
    ws.append(["작업", "가중치", "진척"])
    ws.append(["요구사항 정의", 0.2, 1.0])
    ws.append(["설계", 0.3, 0.5])
    wb.save(path)

    wb2 = load_workbook(path, data_only=True)
    ws2 = wb2["WBS"]
    rows = [[c.value for c in r] for r in ws2.iter_rows()]
    print("시트:", wb2.sheetnames)
    for r in rows:
        print("  |", r)
    return rows[0] == ["작업", "가중치", "진척"] and rows[1][1] == 0.2


def verify_pdf() -> bool:
    band("PDF — pypdf")
    from pypdf import PdfReader, PdfWriter

    # pypdf 로 최소 PDF 를 만들고 다시 읽어 라이브러리 동작을 확인한다
    path = ROOT / "build" / "sample.pdf"
    path.parent.mkdir(exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    # 텍스트를 직접 그리는 건 저수준이라, pypdf 가 최소 텍스트를 읽는지만 본다.
    with open(path, "wb") as f:
        writer.write(f)
    reader = PdfReader(path)
    print(f"페이지 수: {len(reader.pages)}")
    txt = reader.pages[0].extract_text()
    print(f"텍스트 추출 호출 성공(빈 페이지라 내용 없음): {txt == '' or txt is not None}")
    # 라이브러리 동작 자체는 확인됨. 실제 텍스트 PDF 는 샘플 확보 후.
    return len(reader.pages) == 1


def main() -> int:
    results = {}
    results["HWPX 표 추출"] = safe(verify_hwpx)
    results["DOCX"] = safe(verify_docx)
    results["XLSX"] = safe(verify_xlsx)
    results["PDF (동작)"] = safe(verify_pdf)

    hwp_arg = [a for a in sys.argv[1:] if a.lower().endswith(".hwp")]
    if hwp_arg:
        results["HWP5 실파일"] = safe(lambda: verify_hwp5(Path(hwp_arg[0])))

    band("판정 요약")
    for name, ok in results.items():
        print(f"  {'✓' if ok else '✗'}  {name}")
    if not hwp_arg:
        print("\n  ⚠ HWP 5.0 바이너리 실파일 검증은 미완 — 표 있는 공문서 샘플이 필요하다.")
        print("     인자로 넘겨 재실행: verify_doc_parsers.py <공문서.hwp>")
    return 0 if all(results.values()) else 1


def safe(fn) -> bool:
    try:
        return bool(fn())
    except Exception as e:  # noqa: BLE001 — 스파이크라 어느 파서가 왜 죽는지 다 보고한다
        import traceback

        print(f"  ✗ 예외: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    raise SystemExit(main())
