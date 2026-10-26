"""파서 자원 상한 (SWFR.CON.007, 점검 RES-02).

올린 파일 크기만으로는 파서가 쓰는 메모리를 묶지 못한다. 압축 형식은 열기 전에 목록으로 풀린
총량·배율·항목 수를 보고, XLSX 는 행 수, PDF 는 쪽 수에 상한을 둔다. 시험은 상한을 작게 바꿔
작은 정상 파일로 본다. 큰 파일이나 압축 폭탄은 만들지 않는다.
"""

import io
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.document import extractor
from tests.test_extractor_office import _pptx_bytes
from tests.test_extractor_pdf import _pdf_bytes


def _xlsx(tmp_path: Path, rows: int) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "WBS"
    ws.append(["작업", "진척"])
    for n in range(rows):
        ws.append([f"작업 {n}", n])
    path = tmp_path / "wbs.xlsx"
    wb.save(path)
    return path


def _zip(tmp_path: Path, entries: dict[str, bytes], name: str = "x.docx") -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for entry, data in entries.items():
            z.writestr(entry, data)
    path = tmp_path / name
    path.write_bytes(buf.getvalue())
    return path


def test_보통_파일은_상한에_걸리지_않는다(tmp_path):
    path = _xlsx(tmp_path, 3)
    result = extractor.extract(path, "XLSX")
    assert "작업 2" in result.text and result.warning == ""
    pptx = tmp_path / "a.pptx"
    pptx.write_bytes(_pptx_bytes())
    assert "착수보고" in extractor.extract(pptx, "PPTX").text


def test_압축_항목이_너무_많으면_읽지_않는다(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "MAX_ZIP_ENTRIES", 5)
    path = _zip(tmp_path, {f"word/p{n}.xml": b"<a/>" for n in range(6)})
    with pytest.raises(extractor.LimitError, match="항목이 너무 많습니다"):
        extractor.extract(path, "DOCX")


def test_풀린_총량이_상한을_넘으면_읽지_않는다(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "MAX_UNZIPPED_BYTES", 10_000)
    path = _xlsx(tmp_path, 200)  # 풀면 수십 KB
    with pytest.raises(extractor.LimitError, match="너무 큽니다"):
        extractor.extract(path, "XLSX")


def test_압축_배율이_비정상이면_읽지_않는다(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "MAX_ZIP_RATIO", 50)
    # 같은 글자 2MB 는 수 KB 로 줄어든다(배율 수백 배). 풀린 크기 2MB 로 작은 입력이다
    path = _zip(tmp_path, {"word/document.xml": b"a" * (2 * 1024 * 1024)})
    with pytest.raises(extractor.LimitError, match="배율"):
        extractor.extract(path, "DOCX")


def test_압축이_아닌_파일을_압축_형식으로_올리면_손상으로_본다(tmp_path):
    path = tmp_path / "x.docx"
    path.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="손상"):
        extractor.extract(path, "DOCX")


def test_엑셀_행이_상한을_넘으면_앞부분만_읽고_알린다(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "MAX_XLSX_ROWS", 10)
    result = extractor.extract(_xlsx(tmp_path, 50), "XLSX")
    assert "작업 8" in result.text and "작업 9" not in result.text  # 머리행 + 9행
    assert "앞 10행만" in result.warning


def _two_pages() -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for prose in ("First page", "Second page"):
        writer.add_page(PdfReader(io.BytesIO(_pdf_bytes(prose=prose))).pages[0])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_PDF_쪽이_상한을_넘으면_앞쪽만_읽고_알린다(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "MAX_PDF_PAGES", 1)
    path = tmp_path / "a.pdf"
    path.write_bytes(_two_pages())
    result = extractor.extract(path, "PDF")
    assert result.page_count == 2
    assert "<!-- 2쪽 -->" not in result.text and "앞 1쪽만" in result.warning


def test_상한이_넘는_업로드는_통째로_읽지_않는다(monkeypatch):
    from app.document import router

    read: list[int] = []

    class Body:
        def read(self, size: int = -1) -> bytes:
            read.append(size)
            return b"x" * (size if size > 0 else 10)

    class Upload:
        filename = "a.txt"
        file = Body()

    class Stop(Exception):
        pass

    def upload(*_a, **_k):
        raise Stop
    monkeypatch.setattr(router.service, "upload", upload)
    monkeypatch.setattr(router, "tx", lambda: __import__("contextlib").nullcontext(None))
    with pytest.raises(Stop):
        router.upload_document("p", None, Upload())
    assert read == [router.service.MAX_BYTES + 1]
