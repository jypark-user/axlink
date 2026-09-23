"""PPTX·MD·TXT 추출과 PDF 표 찾기 실패 시 본문 보존 (SWFR.CON.007).

착수·중간·최종보고 자료는 pptx 다. 09.23 착수보고 PDF 에서 pdfplumber 가 표 상자 경계로
ValueError 를 내 문서 전체가 실패로 남았다. 쪽 하나의 표를 못 찾아도 글은 남아야 한다.
"""

import io
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from app.document import extractor
from tests.test_extractor_pdf import _pdf_bytes


def _pptx_bytes() -> bytes:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # 제목만
    slide.shapes.title.text = "착수보고"
    box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(1))
    box.text_frame.text = "사업 추진 계획 및 추진내용"
    table = slide.shapes.add_table(2, 2, Inches(1), Inches(3), Inches(6), Inches(1)).table
    table.cell(0, 0).text, table.cell(0, 1).text = "마일스톤", "목표일"
    table.cell(1, 0).text, table.cell(1, 1).text = "M0 착수보고", "2026.08.11"
    slide.notes_slide.notes_text_frame.text = "30분 발표"
    prs.slides.add_slide(prs.slide_layouts[6])  # 빈 슬라이드
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_pptx_는_슬라이드마다_글_표_노트를_남긴다(tmp_path: Path):
    path = tmp_path / "착수보고.pptx"
    path.write_bytes(_pptx_bytes())

    result = extractor.extract(path, "PPTX")

    assert result.page_count == 2 and result.table_count == 1
    assert "<!-- 1쪽 -->" in result.text and "착수보고" in result.text
    assert "사업 추진 계획 및 추진내용" in result.text
    assert "| 마일스톤 | 목표일 |" in result.text and "| M0 착수보고 | 2026.08.11 |" in result.text
    assert "(발표자 노트) 30분 발표" in result.text
    assert "<!-- 2쪽 --> 텍스트 없음" in result.text
    assert result.warning == ""


def test_md_와_txt_는_그대로이고_cp949_도_읽는다(tmp_path: Path):
    md = tmp_path / "메모.md"
    md.write_text("# 제목\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    result = extractor.extract(md, "MD")
    assert result.text.startswith("# 제목") and result.table_count == 1

    txt = tmp_path / "옛날.txt"
    txt.write_bytes("한글 텍스트".encode("cp949"))
    assert extractor.extract(txt, "TXT").text == "한글 텍스트"


def test_지원_형식에_pptx_md_txt_가_들어간다():
    assert extractor.is_supported("보고.pptx") and extractor.is_supported("README.md")
    assert extractor.is_supported("x.TXT") and not extractor.is_supported("x.zip")


def test_pdf_표_찾기가_죽어도_쪽의_글은_남는다(tmp_path: Path, monkeypatch):
    path = tmp_path / "slide.pdf"
    path.write_bytes(_pdf_bytes(prose="Kickoff report"))

    import pdfplumber

    real_open = pdfplumber.open

    class _Broken:
        """슬라이드 PDF 처럼 표 상자가 쪽 경계를 벗어나 find_tables 가 죽는 쪽."""

        def __init__(self, page):
            self._page = page

        def find_tables(self, *a, **k):
            raise ValueError("Bounding box (0.0, -6e-05, 960.0, 539.9) is not fully within parent")

        def __getattr__(self, name):
            return getattr(self._page, name)

    class _Pdf:
        def __init__(self, pdf):
            self._pdf = pdf
            self.pages = [_Broken(p) for p in pdf.pages]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self._pdf.close()

    monkeypatch.setattr(pdfplumber, "open", lambda p: _Pdf(real_open(p)))

    result = extractor.extract(path, "PDF")

    assert result.page_count == 1 and result.table_count == 0
    assert "Kickoff report" in result.text and result.warning == ""
