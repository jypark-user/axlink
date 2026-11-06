"""파일 형식별 텍스트·표 추출. DB 도 네트워크도 모른다 — 파일만 받고 텍스트를 낸다.

파일럿의 Tika(Java) 자리다. 형식마다 라이브러리가 다르지만 결과 모양은 하나로 맞춘다.
표는 전부 마크다운으로 낸다(ARC-001 6절 · RSK-010 으로 검증).

올린 파일 크기(50MB)만으로는 파서가 쓰는 메모리·시간을 묶지 못한다. 압축 형식(DOCX·XLSX·PPTX·
HWPX)은 풀린 크기가 수십 배가 될 수 있다. 그래서 열기 전에 압축 목록을 보고 풀린 총량·배율·
항목 수가 상한을 넘으면 읽지 않는다. XLSX 는 행을 흘려 읽고 행 수에, PDF 는 쪽 수에 상한을 둔다
(점검 RES-02). 파서를 별도 프로세스로 떼거나 처리 시간에 상한을 두는 일은 하지 않았다.
"""

import re
import zipfile
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


# 압축 형식 상한. 실제 산출물(수 MB, 항목 수백 개, 배율 10배 안팎)보다 넉넉하게 잡았다
ZIP_EXTS = frozenset({"DOCX", "XLSX", "PPTX", "HWPX"})
MAX_UNZIPPED_BYTES = 500 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_RATIO = 200  # 풀린 크기 / 압축 크기. 1MB 이하로 풀리는 파일은 보지 않는다
MAX_XLSX_ROWS = 200_000  # 시트를 합친 값 있는 행
MAX_PDF_PAGES = 2_000


class LimitError(ValueError):
    """파일이 처리 상한을 넘었다. 메시지가 그대로 문서의 처리 실패 이유가 된다."""


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
    if ext.upper() in ZIP_EXTS:
        check_zip(path)
    return handler(path)


def check_zip(path: Path) -> None:
    """압축을 풀기 전에 목록만 보고 상한을 넘는지 본다. 넘으면 LimitError."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
    except zipfile.BadZipFile as exc:
        raise ValueError("파일이 손상됐거나 형식이 확장자와 다릅니다.") from exc
    if len(infos) > MAX_ZIP_ENTRIES:
        raise LimitError(
            f"파일 안 항목이 너무 많습니다({len(infos):,}개, 상한 {MAX_ZIP_ENTRIES:,}개)."
        )
    unpacked = sum(i.file_size for i in infos)
    packed = max(1, sum(i.compress_size for i in infos))
    if unpacked > MAX_UNZIPPED_BYTES:
        raise LimitError(
            f"압축을 풀면 너무 큽니다({unpacked // 1024 // 1024:,}MB, "
            f"상한 {MAX_UNZIPPED_BYTES // 1024 // 1024:,}MB)."
        )
    if unpacked > 1024 * 1024 and unpacked / packed > MAX_ZIP_RATIO:
        raise LimitError(
            f"압축 배율이 비정상적으로 큽니다({unpacked // packed:,}배, 상한 {MAX_ZIP_RATIO}배)."
        )


def _hwp5(path: Path) -> ExtractResult:
    from hwp_hwpx_parser import ExtractOptions, HWP5Reader, TableStyle, extract_hwp5

    text, err = extract_hwp5(path, ExtractOptions(table_style=TableStyle.MARKDOWN))
    return ExtractResult(text, len(HWP5Reader(path).get_tables()), warning=err or "")


def _hwpx(path: Path) -> ExtractResult:
    from hwp_hwpx_parser import ExtractOptions, HWPXReader, TableStyle, extract_hwpx

    text, err = extract_hwpx(path, ExtractOptions(table_style=TableStyle.MARKDOWN))
    return ExtractResult(text, len(HWPXReader(path).get_tables()), warning=err or "")


# DOCX 표제 스타일 이름. 영문 기본 이름(Heading 1)과 한글판에서 바꿔 단 이름(제목 1)을 함께 본다
_DOCX_HEADING = re.compile(r"^(?:heading|제목)\s*(\d)$", re.IGNORECASE)


def _docx_heading_level(paragraph) -> int | None:
    name = ((paragraph.style.name if paragraph.style is not None else "") or "").strip()
    if name.lower() == "title":
        return 1
    m = _DOCX_HEADING.match(name)
    return min(int(m.group(1)), 6) if m else None


def _docx(path: Path) -> ExtractResult:
    """본문 순서대로 문단과 표를 낸다. 표제 스타일 문단은 마크다운 표제로 남긴다.

    청킹은 표제로 절 경로를 만든다. 스타일을 버리면 출처 위치(「논의 사항」 같은 절)가
    비고, 표를 끝으로 몰면 표가 어느 절에 있었는지 잃는다(AC-060-11).
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    parts: list[str] = []
    tables = 0
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            if not para.text.strip():
                continue
            level = _docx_heading_level(para)
            parts.append(f"{'#' * level} {para.text.strip()}" if level else para.text)
        elif tag == "tbl":
            rows = [[c.text.strip() for c in r.cells] for r in Table(child, doc).rows]
            parts.append(markdown_table(rows))
            tables += 1
    return ExtractResult("\n\n".join(parts), tables)


# XLSX 표의 첫 열 이름. 엑셀 행 번호가 들어가고, 청킹이 이 이름으로 그 열을 알아본다
ROW_COLUMN = "행"


def _xlsx(path: Path) -> ExtractResult:
    from openpyxl import load_workbook

    # read_only 는 행을 흘려 읽는다. 시트 전체를 메모리에 올리지 않는다
    wb = load_workbook(path, data_only=True, read_only=True)
    parts, sheets, total, cut = [], 0, 0, False
    try:
        for name in wb.sheetnames:
            rows = []
            for no, row in enumerate(wb[name].iter_rows(values_only=True), 1):
                if all(v is None for v in row):
                    continue
                if total >= MAX_XLSX_ROWS:
                    cut = True
                    break
                # 첫 칸에 엑셀 행 번호를 둔다. 빈 행을 건너뛰어도 원본 행을 가리키게 하려는
                # 것이고, 청킹이 이 번호로 조각의 행 범위를 남긴다(SWFR.RAG.003). 첫 행은 표
                # 머리글이라 번호 대신 열 이름을 적는다
                cells = ["" if v is None else str(v) for v in row]
                rows.append([ROW_COLUMN if not rows else str(no), *cells])
                total += 1
            if rows:
                sheets += 1
                # 시트 이름을 표제로 남긴다 — 청킹이 이걸 원문 위치로 쓴다.
                parts.append(f"## 시트: {name}\n\n{markdown_table(rows)}")
            if cut:
                break
    finally:
        wb.close()
    warning = f"행이 많아 앞 {MAX_XLSX_ROWS:,}행만 읽었습니다." if cut else ""
    return ExtractResult("\n\n".join(parts), sheets, warning=warning)


def _pdf(path: Path) -> ExtractResult:
    """쪽마다 본문과 표를 따로 뽑는다. 표는 괘선으로 찾고, 표 안 글자는 본문에서 뺀다.

    본문에 표 셀까지 섞이면 같은 값이 두 번 색인되고 행·열 구조도 잃는다. 괘선 없는 표는
    못 찾는다. 그건 본문으로 남는다.
    """
    import pdfplumber

    pages, found, table_count = [], False, 0
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages[:MAX_PDF_PAGES], 1):
            chunks, tables_found = _pdf_page(page)
            table_count += tables_found
            found = found or bool(chunks)
            if chunks:
                pages.append(f"<!-- {i}쪽 -->\n" + "\n\n".join(chunks))
            else:
                pages.append(f"<!-- {i}쪽 --> 텍스트 없음")
    # 스캔본은 페이지는 있는데 글자가 하나도 안 나온다. OCR 은 범위 밖이라 판별만 한다.
    warning = "" if found else "텍스트가 추출되지 않았습니다 — 스캔 이미지 PDF 로 보입니다."
    if page_count > MAX_PDF_PAGES:
        warning = f"쪽이 많아 앞 {MAX_PDF_PAGES:,}쪽만 읽었습니다. {warning}".strip()
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
