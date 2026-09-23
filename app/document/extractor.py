"""파일 형식별 텍스트·표 추출. DB 도 네트워크도 모른다 — 파일만 받고 텍스트를 낸다.

파일럿의 Tika(Java) 자리다. 형식마다 라이브러리가 다르지만 결과 모양은 하나로 맞춘다.
표는 전부 마크다운으로 낸다(ARC-001 6절 · RSK-010 으로 검증).
"""

from dataclasses import dataclass
from pathlib import Path

# DB ck_document_upload__file_ext 와 같은 집합이어야 한다.
SUPPORTED_EXTS = ("HWP", "HWPX", "DOCX", "XLSX", "PPTX", "PDF", "MD", "TXT")

MIME_BY_EXT = {
    "HWP": "application/x-hwp",
    "HWPX": "application/hwp+zip",
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "PDF": "application/pdf",
    "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "MD": "text/markdown",
    "TXT": "text/plain",
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
        "PPTX": _pptx,
        "PDF": _pdf,
        "MD": _text,
        "TXT": _text,
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
            chunks, tables_found = _pdf_page(page)
            table_count += tables_found
            found = found or bool(chunks)
            if chunks:
                pages.append(f"<!-- {i}쪽 -->\n" + "\n\n".join(chunks))
            else:
                pages.append(f"<!-- {i}쪽 --> 텍스트 없음")
    # 스캔본은 페이지는 있는데 글자가 하나도 안 나온다. OCR 은 범위 밖이라 판별만 한다.
    warning = "" if found else "텍스트가 추출되지 않았습니다 — 스캔 이미지 PDF 로 보입니다."
    return ExtractResult("\n\n".join(pages), table_count, page_count=page_count, warning=warning)


def _pdf_page(page) -> tuple[list[str], int]:
    """쪽 하나의 본문과 표. 표 찾기가 죽으면 글자만이라도 뽑는다.

    슬라이드를 PDF 로 내보낸 파일은 표 상자가 쪽 경계를 아주 조금 벗어나 pdfplumber 가
    ValueError 를 낸다(09.23 착수보고 PDF). 그 때문에 쪽 전체를 잃으면 안 된다.
    """
    try:
        tables = page.find_tables()
        x0, top, x1, bottom = page.bbox
        prose = page
        for table in tables:
            bx0, btop, bx1, bbottom = table.bbox
            # 쪽 경계 안으로 눌러 넣는다. 부동소수 오차로 몇 천분의 일 포인트 벗어나는 경우다
            clamped = (max(bx0, x0), max(btop, top), min(bx1, x1), min(bbottom, bottom))
            prose = prose.outside_bbox(clamped)
        body = (prose.extract_text() or "").strip()
        chunks = [body] if body else []
        count = 0
        for table in tables:
            rows = [
                ["" if cell is None else " ".join(str(cell).split()) for cell in row]
                for row in table.extract()
            ]
            rows = [r for r in rows if any(r)]
            if rows:
                chunks.append(markdown_table(rows))
                count += 1
        return chunks, count
    except ValueError:
        body = (page.extract_text() or "").strip()
        return ([body] if body else []), 0


def _pptx(path: Path) -> ExtractResult:
    """슬라이드마다 글과 표. 쪽 표식은 슬라이드 번호다. 노트도 본문 뒤에 붙인다."""
    from pptx import Presentation

    prs = Presentation(path)
    parts, table_count, found = [], 0, False
    for i, slide in enumerate(prs.slides, 1):
        chunks: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                lines = [
                    " ".join(p.text.split()) for p in shape.text_frame.paragraphs if p.text.strip()
                ]
                if lines:
                    chunks.append("\n".join(lines))
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [
                    [" ".join(c.text.split()) for c in row.cells] for row in shape.table.rows
                ]
                rows = [r for r in rows if any(r)]
                if rows:
                    chunks.append(markdown_table(rows))
                    table_count += 1
        if slide.has_notes_slide:
            note = " ".join(slide.notes_slide.notes_text_frame.text.split())
            if note:
                chunks.append(f"(발표자 노트) {note}")
        found = found or bool(chunks)
        parts.append(
            f"<!-- {i}쪽 -->\n" + "\n\n".join(chunks) if chunks else f"<!-- {i}쪽 --> 텍스트 없음"
        )
    warning = "" if found else "텍스트가 추출되지 않았습니다. 그림만 있는 슬라이드 같습니다."
    return ExtractResult(
        "\n\n".join(parts), table_count, page_count=len(prs.slides), warning=warning
    )


def _text(path: Path) -> ExtractResult:
    """마크다운·텍스트는 그대로다. 한글 인코딩이 섞여 있어 utf-8 이 안 되면 cp949 로 읽는다."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    tables = sum(1 for line in text.splitlines() if line.strip().startswith("|---"))
    return ExtractResult(text.strip(), tables)


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
