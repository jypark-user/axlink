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
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages, found = [], False
    for i, page in enumerate(reader.pages, 1):
        body = (page.extract_text() or "").strip()
        found = found or bool(body)
        pages.append(f"<!-- {i}쪽 -->\n{body}" if body else f"<!-- {i}쪽 --> 텍스트 없음")
    # 스캔본은 페이지는 있는데 글자가 하나도 안 나온다. OCR 은 범위 밖이라 판별만 한다.
    warning = "" if found else "텍스트가 추출되지 않았습니다 — 스캔 이미지 PDF 로 보입니다."
    return ExtractResult("\n\n".join(pages), 0, page_count=len(reader.pages), warning=warning)


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
