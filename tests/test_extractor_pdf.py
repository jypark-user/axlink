"""PDF 표 추출 (SWFR.CON.007). 괘선이 있는 표는 행·열 구조로, 나머지는 본문으로 남는다.

PDF 는 라이브러리 없이 손으로 만든다. 객체 몇 개와 xref 표만 맞추면 되고, 시험이 무엇을
그렸는지가 파일 안에 그대로 보인다.
"""

from pathlib import Path

from app.document import extractor


def _pdf_bytes(*, with_table: bool = True, prose: str = "Progress report") -> bytes:
    """A4 한 쪽. 위에 문장 한 줄, 아래에 2x2 표(괘선 포함)."""
    ops = [f"BT /F1 12 Tf 100 760 Td ({prose}) Tj ET"]
    if with_table:
        x0, x1, x2 = 100, 250, 400
        ys = [700, 680, 660]
        ops.append("0.5 w")
        for y in ys:
            ops.append(f"{x0} {y} m {x2} {y} l S")
        for x in (x0, x1, x2):
            ops.append(f"{x} {ys[0]} m {x} {ys[-1]} l S")
        cells = [("Task", "Weight"), ("Design", "0.3")]
        for row, (left, right) in zip(ys[:-1], cells, strict=True):
            ops.append(f"BT /F1 10 Tf {x0 + 8} {row - 14} Td ({left}) Tj ET")
            ops.append(f"BT /F1 10 Tf {x1 + 8} {row - 14} Td ({right}) Tj ET")
    stream = "\n".join(ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_괘선_표는_행열_구조로_남고_본문과_섞이지_않는다(tmp_path: Path):
    path = tmp_path / "report.pdf"
    path.write_bytes(_pdf_bytes())

    result = extractor.extract(path, "PDF")

    assert result.page_count == 1 and result.table_count == 1
    assert "<!-- 1쪽 -->" in result.text
    assert "Progress report" in result.text
    assert "| Task | Weight |" in result.text
    assert "| Design | 0.3 |" in result.text
    # 표 셀 글자는 본문 줄에 다시 나오지 않는다. 두 번 색인되면 같은 값이 두 근거가 된다
    assert result.text.count("Design") == 1
    assert result.warning == ""


def test_표_없는_쪽은_본문만_나온다(tmp_path: Path):
    path = tmp_path / "plain.pdf"
    path.write_bytes(_pdf_bytes(with_table=False))

    result = extractor.extract(path, "PDF")

    assert result.table_count == 0
    assert "Progress report" in result.text and "|" not in result.text


def test_글자_없는_쪽은_스캔본으로_본다(tmp_path: Path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf_bytes(with_table=False, prose=""))

    result = extractor.extract(path, "PDF")

    assert "텍스트 없음" in result.text
    assert "스캔" in result.warning
