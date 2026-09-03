#!/usr/bin/env python3
"""문서에서 텍스트와 표를 뽑아 눈으로 확인한다.

파일 하나든 폴더든 넘기면 추출 결과를 마크다운으로 저장한다. 한글(HWP·HWPX)·
워드·엑셀·PDF 를 모두 같은 방식으로 처리한다. 원본을 한글에서 열어 놓고
나온 마크다운과 나란히 보면 표가 제대로 갈라졌는지 바로 보인다.

    .venv/Scripts/python scripts/extract_doc.py "C:/경로/공문서.hwp"
    .venv/Scripts/python scripts/extract_doc.py "C:/Users/나/Downloads"
    .venv/Scripts/python scripts/extract_doc.py 문서.hwp --chunks

--chunks 를 붙이면 RAG 가 이 문서를 어떻게 쪼개는지까지 보여준다.
결과는 build/extracted/ 아래에 쌓인다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "build" / "extracted"

SUPPORTED = {".hwp", ".hwpx", ".docx", ".xlsx", ".pdf"}


def _utf8_console() -> None:
    """윈도우 콘솔 기본 코드페이지가 cp949 라 한글이 깨진다. 출력만 UTF-8 로 돌린다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def extract(path: Path) -> tuple[str, list, str]:
    """(본문 마크다운, 표 목록, 경고) 를 돌려준다. 표가 없는 형식은 빈 목록."""
    ext = path.suffix.lower()

    if ext in (".hwp", ".hwpx"):
        from hwp_hwpx_parser import (
            ExtractOptions,
            HWP5Reader,
            HWPXReader,
            TableStyle,
            extract_hwp5,
            extract_hwpx,
        )

        opts = ExtractOptions(table_style=TableStyle.MARKDOWN)
        if ext == ".hwp":
            text, err = extract_hwp5(path, opts)
            tables = HWP5Reader(path).get_tables()
        else:
            text, err = extract_hwpx(path, opts)
            tables = HWPXReader(path).get_tables()
        return text, tables, err or ""

    if ext == ".docx":
        from docx import Document

        doc = Document(path)
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        tables = []
        for t in doc.tables:
            rows = [[c.text.strip() for c in r.cells] for r in t.rows]
            tables.append(_Table(rows))
            parts.append(_markdown_table(rows))
        return "\n\n".join(parts), tables, ""

    if ext == ".xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(path, data_only=True)
        parts, tables = [], []
        for name in wb.sheetnames:
            ws = wb[name]
            rows = [
                ["" if c.value is None else str(c.value) for c in r]
                for r in ws.iter_rows()
                if any(c.value is not None for c in r)
            ]
            if not rows:
                continue
            parts.append(f"## 시트: {name}\n\n{_markdown_table(rows)}")
            tables.append(_Table(rows))
        return "\n\n".join(parts), tables, ""

    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages, found = [], False
        for i, page in enumerate(reader.pages, 1):
            body = (page.extract_text() or "").strip()
            found = found or bool(body)
            head = f"<!-- {i}쪽 -->"
            pages.append(f"{head}\n{body}" if body else f"{head} 텍스트 없음")
        # 스캔본은 페이지는 있는데 글자가 하나도 안 나온다. OCR 이 필요한 경우다.
        warn = "" if found else "텍스트가 안 나온다 — 스캔 이미지 PDF 일 수 있다"
        return "\n\n".join(pages), [], warn

    raise ValueError(f"지원하지 않는 형식: {ext}")


class _Table:
    """표 개수·행수만 세면 되므로 파서별 표 객체를 이 모양으로 맞춘다."""

    def __init__(self, rows: list[list[str]]) -> None:
        self.rows = rows


def _markdown_table(rows: list[list[str]]) -> str:
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


def report(path: Path, show_chunks: bool) -> bool:
    print(f"\n{'=' * 68}\n{path.name}  ({path.stat().st_size / 1024:,.0f} KB)")
    try:
        text, tables, warn = extract(path)
    except Exception as exc:  # noqa: BLE001 — 어느 파일이 왜 깨지는지 다 보여주는 게 목적이다
        print(f"  실패 — {type(exc).__name__}: {exc}")
        return False

    print(f"  텍스트 {len(text):,}자 · 표 {len(tables)}개")
    if warn:
        print(f"  경고: {warn}")

    if tables:
        biggest = max(tables, key=lambda t: len(t.rows))
        print(f"  가장 큰 표 {len(biggest.rows)}행 — 앞 3행:")
        for row in biggest.rows[:3]:
            print("      " + " | ".join(str(c)[:24] for c in row))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{path.stem}.md"
    out.write_text(f"# {path.name}\n\n{text}\n", encoding="utf-8")
    print(f"  저장 → {out}")

    if show_chunks:
        sys.path.insert(0, str(ROOT))
        from app.rag import chunking

        drafts = chunking.chunk("DOCUMENT_UPLOAD", path.stem, text)
        toks = [d.token_count for d in drafts] or [0]
        print(f"  RAG 청크 {len(drafts)}개 · 토큰 최소 {min(toks)} / 최대 {max(toks)}")
        for d in drafts[:3]:
            where = " > ".join(d.meta["headingPath"]) or "(표제 없음)"
            print(f"      [{d.chunk_index}] {where[:44]} — {d.content[:46]}...".replace("\n", " "))

    return len(text) > 0


def collect(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*") if p.suffix.lower() in SUPPORTED)


def main() -> int:
    _utf8_console()
    ap = argparse.ArgumentParser(description="문서 추출 결과를 눈으로 확인한다")
    ap.add_argument("target", help="파일 또는 폴더 경로")
    ap.add_argument("--chunks", action="store_true", help="RAG 청킹 결과까지 보여준다")
    ap.add_argument("--limit", type=int, default=20, help="폴더일 때 처리할 최대 파일 수")
    args = ap.parse_args()

    target = Path(args.target).expanduser()
    if not target.exists():
        print(f"경로가 없다: {target}")
        return 1

    files = collect(target)[: args.limit]
    if not files:
        print(f"처리할 문서가 없다. 지원 형식: {', '.join(sorted(SUPPORTED))}")
        return 1

    ok = sum(report(f, args.chunks) for f in files)
    print(f"\n{'=' * 68}\n{len(files)}개 중 {ok}개 추출 성공. 결과: {OUT_DIR}")
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
