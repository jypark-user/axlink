"""IM-005A TD-DOC-16 스캔문서.pdf 를 만든다. 가상 시험자료다.

정상 가상 문서(이 폴더의 과업지시서.pdf, TD-DOC-4) 1쪽을 그림으로 렌더링해 글자 층이 없는
그림 PDF 로 다시 싼다. 종이 문서를 스캐너로 읽은 PDF 와 같은 꼴이다(쪽은 있고 뽑을 글자는 없다).
렌더링한 쪽 머리에 「가상 시험자료 · 실제 계약 문서가 아님」이 그대로 찍혀 있다.

    python tests/fixtures/im009/pdf/make_scan_pdf.py

같은 입력이면 같은 해시가 나온다(생성 시각을 넣지 않는다). 해시는 README.md.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pypdfium2 as pdfium

HERE = Path(__file__).parent
SOURCE = HERE / "과업지시서.pdf"
OUT = HERE / "스캔문서.pdf"
DPI = 150


def make(out: Path = OUT) -> Path:
    pdf = pdfium.PdfDocument(str(SOURCE))
    try:
        image = pdf[0].render(scale=DPI / 72).to_pil().convert("L")  # 흑백 스캔
    finally:
        pdf.close()
    buf = io.BytesIO()
    image.save(buf, "PDF", resolution=DPI)
    out.write_bytes(buf.getvalue())
    return out


if __name__ == "__main__":
    path = make()
    print(path.name, hashlib.sha256(path.read_bytes()).hexdigest())
