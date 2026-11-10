"""IM-009 시험자료 PDF 두 건(TD-DOC-4·TD-DOC-7)을 만든다. 둘 다 가상 시험자료다.

만든 PDF 는 이 폴더에 커밋해 두고 시험은 그 파일을 쓴다(files.py). 다시 만들 때만 이 스크립트를
돌린다. 글꼴 파일은 저장소에 넣지 않는다. 제작 절차·글꼴·해시는 README.md.

    python tests/fixtures/im009/pdf/make_pdfs.py --font <NotoSansKR 정적 TTF 경로>

글꼴은 Noto Sans KR(SIL OFL 1.1). Windows 에 깔린 가변 글꼴(NotoSansKR-VF.ttf)이면
--variable 로 넘기면 굵기 400 정적 인스턴스를 임시 폴더에 만들어 쓴다.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
FONT = "NotoSansKR"
MARK = "가상 시험자료 · 실제 계약 문서가 아님 · AX Link 검증용(IM-009 {tid})"
W, H = A4


def _static_font(variable: Path, out_dir: Path) -> Path:
    """가변 글꼴에서 굵기 400 정적 인스턴스를 만든다(reportlab 은 가변 축을 모른다)."""
    from fontTools.ttLib import TTFont as FtFont
    from fontTools.varLib import instancer

    # 시각을 고정해야 같은 입력에서 같은 PDF(해시)가 나온다
    source = FtFont(str(variable), recalcTimestamp=False)
    font = instancer.instantiateVariableFont(source, {"wght": 400})
    path = out_dir / "NotoSansKR-Regular-instance.ttf"
    font.save(str(path))
    return path


def _page(c: canvas.Canvas, tid: str, no: int, total: int) -> None:
    c.setFont(FONT, 8.5)
    c.setFillGray(0.35)
    c.drawString(56, H - 40, MARK.format(tid=tid))
    c.drawCentredString(W / 2, 32, f"- {no} / {total} -")
    c.setFillGray(0)


def _lines(c: canvas.Canvas, y: float, lines: list[tuple[float, str]], gap: float = 22) -> float:
    for size, text in lines:
        c.setFont(FONT, size)
        c.drawString(56, y, text)
        y -= gap if size < 14 else gap + 10
    return y


def sow(path: Path) -> Path:
    """TD-DOC-4 과업지시서.pdf. 3쪽.

    IM-009 4.2·7.5: 2쪽 「2. 납품 산출물」 「납품 산출물은 22종이다」, 3쪽 「3. 사업 기간」
    「사업 기간은 9개월이다」. 「사업 기간」은 3쪽에만 있다(7.5 의 쪽 번호 판정이 이걸 본다).
    """
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle("과업지시서(가상 시험자료)")
    c.setAuthor("AX Link 검증 시험자료")
    c.setSubject("IM-009 TD-DOC-4. 실제 계약 문서가 아님")
    pages = [
        [
            (18, "시민포털 고도화 과업지시서"),
            (11, "이 문서는 AX Link 검증을 위해 만든 가상 시험자료다. 실제 발주 문서가 아니다."),
            (14, "1. 개요"),
            (11, "본 과업은 가람시 시민포털의 통합 로그인과 민원 조회 기능을 고도화한다."),
            (11, "용역사는 요구사항 정의, 설계, 구현, 시험, 인도의 순서로 과업을 수행한다."),
            (11, "과업의 범위와 산출물, 일정은 다음 절에서 정한다."),
        ],
        [
            (14, "2. 납품 산출물"),
            (11, "납품 산출물은 22종이다."),
            (11, "용역사는 산출물마다 정한 시점에 제출한다."),
            (11, "산출물은 발주기관의 검토와 승인을 거쳐 확정한다."),
        ],
        [
            (14, "3. 사업 기간"),
            (11, "사업 기간은 9개월이다."),
            (11, "용역사는 착수일부터 정한 기간 안에 모든 과업을 마치고 최종 산출물을 인도한다."),
            (11, "기간 변경은 발주기관과 협의해 문서로 정한다."),
        ],
    ]
    for no, lines in enumerate(pages, start=1):
        _page(c, "TD-DOC-4", no, len(pages))
        _lines(c, H - 96, lines)
        c.showPage()
    c.save()
    return path


def card_spec(path: Path) -> Path:
    """TD-DOC-7 카드형-명세서.pdf. 1쪽.

    IM-009 4.4: 표 없이 카드형 서술, 코드가 줄 머리에 없다. 요구사항 세 건이 카드 하나씩이다.
    코드는 「식별」 뒤에 적는다. 사람은 읽을 수 있고 글자도 뽑히는 정상 문서다.
    """
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle("요구사항 명세서 카드형(가상 시험자료)")
    c.setAuthor("AX Link 검증 시험자료")
    c.setSubject("IM-009 TD-DOC-7. 실제 계약 문서가 아님")
    _page(c, "TD-DOC-7", 1, 1)
    y = _lines(c, H - 96, [
        (18, "알림 서비스 요구사항 명세서(카드형)"),
        (11, "요구사항을 카드 한 장에 하나씩 적었다. 카드마다 식별 코드와 중요도를 함께 둔다."),
    ])
    cards = [
        ("알림 수신 설정", "UR.CARD.001", "필수",
         "시민은 민원 처리 알림을 받을 방법(문자, 앱)을 고를 수 있다."),
        ("처리 결과 알림", "UR.CARD.002", "필수",
         "민원 처리가 끝나면 시민이 고른 방법으로 결과를 알린다."),
        ("알림 이력 조회", "UR.CARD.003", "권장",
         "시민은 지난 30일 동안 받은 알림을 목록으로 볼 수 있다."),
    ]
    y -= 6
    for title, code, priority, body in cards:
        top = y
        c.setStrokeGray(0.6)
        c.roundRect(50, top - 92, W - 100, 100, 8, stroke=1, fill=0)
        c.setFont(FONT, 13)
        c.drawString(66, top - 16, f"■ {title}")
        c.setFont(FONT, 10.5)
        c.drawString(66, top - 40, f"카드 식별: {code}  ·  중요도: {priority}")
        c.drawString(66, top - 62, f"내용: {body}")
        y = top - 116
    c.showPage()
    c.save()
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", type=Path, help="Noto Sans KR 정적 TTF")
    ap.add_argument("--variable", type=Path, help="Noto Sans KR 가변 TTF(NotoSansKR-VF.ttf)")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        font = a.font or _static_font(a.variable, Path(tmp))
        pdfmetrics.registerFont(TTFont(FONT, str(font)))
        for fn, name in ((sow, "과업지시서.pdf"), (card_spec, "카드형-명세서.pdf")):
            p = fn(HERE / name)
            print(name, hashlib.sha256(p.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
