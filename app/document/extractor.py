"""파일 형식별 텍스트·표 추출. DB 도 네트워크도 모른다 — 파일만 받고 텍스트를 낸다.

파일럿의 Tika(Java) 자리다. 형식마다 라이브러리가 다르지만 결과 모양은 하나로 맞춘다.
표는 전부 마크다운으로 낸다(ARC-001 6절 · RSK-010 으로 검증).
"""

from dataclasses import dataclass
from pathlib import Path

# DB ck_document_upload__file_ext 와 같은 집합이어야 한다.
SUPPORTED_EXTS = ("HWP", "HWPX", "DOCX", "XLSX", "PDF")

MIME_BY_EXT = {
    "HWP": "application/x-hwp",
    "HWPX": "application/hwp+zip",
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "PDF": "application/pdf",
}


@dataclass
class ExtractResult:
    text: str
    table_count: int
    page_count: int | None = None
    warning: str = ""


def ext_of(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").upper()


def is_supported(filename: str) -> bool:
    return ext_of(filename) in SUPPORTED_EXTS


def extract(path: Path, ext: str) -> ExtractResult:
    """형식에 맞는 파서로 본문을 뽑는다. 지원하지 않는 형식이면 ValueError."""
    handler = {
        "HWP": _hwp5,
        "HWPX": _hwpx,
        "DOCX": _docx,
        "XLSX": _xlsx,
        "PDF": _pdf,
    }.get(ext.upper())
    if handler is None:
        raise ValueError(f"지원하지 않는 형식입니다: {ext}")
    return handler(path)


def _hwp5(path: Path) -> ExtractResult:
    from hwp_hwpx_parser import ExtractOptions, HWP5Reader, TableStyle, extract_hwp5

    text, err = extract_hwp5(path, ExtractOptions(table_style=TableStyle.MARKDOWN))
    return ExtractResult(text, len(HWP5Reader(path).get_tables()), warning=err or "")


def _hwpx(path: Path) -> ExtractResult:
    from hwp_hwpx_parser import ExtractOptions, HWPXReader, TableStyle, extract_hwpx

    text, err = extract_hwpx(path, ExtractOptions(table_style=TableStyle.MARKDOWN))
    return ExtractResult(text, len(HWPXReader(path).get_tables()), warning=err or "")


def _docx(path: Path) -> ExtractResult:
    from docx import Document

    doc = Document(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        rows = [[c.text.strip() for c in r.cells] for r in table.rows]
        parts.append(markdown_table(rows))
    return ExtractResult("\n\n".join(parts), len(doc.tables))


def _xlsx(path: Path) -> ExtractResult:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    parts, sheets = [], 0
    for name in wb.sheetnames:
        rows = [
            ["" if c.value is None else str(c.value) for c in row]
            for row in wb[name].iter_rows()
            if any(c.value is not None for c in row)
        ]
        if not rows:
            continue
        sheets += 1
        # 시트 이름을 표제로 남긴다 — 청킹이 이걸 원문 위치로 쓴다.
        parts.append(f"## 시트: {name}\n\n{markdown_table(rows)}")
    return ExtractResult("\n\n".join(parts), sheets)


def _pdf(path: Path) -> ExtractResult:
    """쪽마다 본문과 표를 따로 뽑는다. 표는 괘선으로 찾고, 표 안 글자는 본문에서 뺀다.

    본문에 표 셀까지 섞이면 같은 값이 두 번 색인되고 행·열 구조도 잃는다. 괘선 없는 표는
    못 찾는다. 그건 본문으로 남는다.
    """
    import pdfplumber

    pages, found, table_count = [], False, 0
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            tables = page.find_tables()
            prose = page
            for table in tables:
                prose = prose.outside_bbox(table.bbox)
            body = (prose.extract_text() or "").strip()
            chunks = [body] if body else []
            for table in tables:
                rows = [
                    ["" if cell is None else " ".join(str(cell).split()) for cell in row]
                    for row in table.extract()
                ]
                rows = [r for r in rows if any(r)]
                if rows:
                    chunks.append(markdown_table(rows))
                    table_count += 1
            found = found or bool(chunks)
            if chunks:
                pages.append(f"<!-- {i}쪽 -->\n" + "\n\n".join(chunks))
            else:
                pages.append(f"<!-- {i}쪽 --> 텍스트 없음")
    # 스캔본은 페이지는 있는데 글자가 하나도 안 나온다. OCR 은 범위 밖이라 판별만 한다.
    warning = "" if found else "텍스트가 추출되지 않았습니다 — 스캔 이미지 PDF 로 보입니다."
    return ExtractResult("\n\n".join(pages), table_count, page_count=page_count, warning=warning)


def markdown_table(rows: list[list[str]]) -> str:
    """행·열 구조를 마크다운 표로 보존한다. 셀 수가 들쭉날쭉하면 빈 칸으로 채운다."""
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    out = []
    for i, row in enumerate(rows):
        cells = [*row, *([""] * (width - len(row)))]
        out.append("| " + " | ".join(cells) + " |")
        if i == 0:
            out.append("| " + " | ".join(["---"] * width) + " |")
    return "\n".join(out)
