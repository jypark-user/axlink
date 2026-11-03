"""청킹 규칙 검증. 모델도 DB도 필요 없다 — 순수 계산이라 여기서 다 잡는다."""

from app.config import settings
from app.rag import chunking


def test_requirement_is_single_chunk_with_title():
    drafts = chunking.chunk("REQUIREMENT", "[SWFR.RAG.004] 한국어 임베딩", "본문이다.")
    assert len(drafts) == 1
    assert drafts[0].content.startswith("[SWFR.RAG.004]")
    assert "본문이다." in drafts[0].content


def test_empty_body_falls_back_to_title():
    drafts = chunking.chunk("ISSUE", "제목만 있는 이슈", None)
    assert len(drafts) == 1
    assert drafts[0].content == "제목만 있는 이슈"


def test_nothing_to_index_returns_empty():
    assert chunking.chunk("ISSUE", "", "") == []


def test_heading_path_is_preserved():
    body = "\n".join(
        [
            "# 1장 개요",
            "개요 문단이다.",
            "## 1.1 목적",
            "목적 문단이다.",
            "# 2장 설계",
            "설계 문단이다.",
        ]
    )
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "설계서", body)
    paths = [d.meta["headingPath"] for d in drafts]
    assert ["1장 개요"] in paths
    assert ["1장 개요", "1.1 목적"] in paths
    assert ["2장 설계"] in paths


def test_long_body_splits_and_overlaps():
    sentence = "이 문장은 청킹 경계를 만들기 위한 충분히 긴 한국어 문장이다. "
    body = sentence * 400  # 목표 토큰을 여러 배 넘긴다
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "긴 문서", body)

    assert len(drafts) > 1
    assert [d.chunk_index for d in drafts] == list(range(len(drafts)))
    for draft in drafts:
        assert draft.token_count <= settings.chunk_max_tokens

    # 오버랩 — 앞 청크의 꼬리가 다음 청크 머리에 남아 있어야 한다.
    assert drafts[0].content[-40:] in drafts[1].content


def test_uneven_sentences_never_exceed_max():
    """실제 공문서(HWP)에서 잡힌 경로 — 긴 문장 뒤 오버랩이 붙어 최대치를 넘겼다."""
    short = "짧은 문장이다. "
    long_one = "가" * 2000 + ". "
    body = (short * 30 + long_one) * 6

    for draft in chunking.chunk("DOCUMENT_UPLOAD", "들쭉날쭉 문서", body):
        assert draft.token_count <= settings.chunk_max_tokens, draft.token_count


def test_oversized_single_sentence_is_cut():
    """표나 URL 덩어리처럼 문장 경계가 없는 입력도 최대치를 넘기지 않는다."""
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "표", "가" * 20000)
    assert len(drafts) > 1
    for draft in drafts:
        assert draft.token_count <= settings.chunk_max_tokens


def test_date_line_is_not_a_heading():
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "회의록", "2026. 8. 29 회의를 열었다.\n논의했다.")
    assert all(d.meta["headingPath"] == [] for d in drafts)


def test_numbered_prefix_does_not_split_a_line():
    """공문서의 '비고  1. …' 은 한 문장이다. 번호 뒤 마침표에서 끊으면 원문이 파편난다."""
    body = "비고  1. 소프트웨어기술자란 자격을 취득한 자를 말한다. 다음 항을 본다."
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "규정", body)
    joined = "\n".join(d.content for d in drafts)
    assert "비고  1. 소프트웨어기술자란" in joined


def test_sentence_end_still_splits():
    """숫자 예외가 일반 문장 분리까지 막으면 안 된다."""
    long_sentence = "이 문장은 청크 경계를 만들기 위한 충분히 긴 한국어 문장이다. "
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "긴 글", long_sentence * 300)
    assert len(drafts) > 1


# ---------------------------------------------------------------- 원문 위치 (SWFR.RAG.003)


def test_쪽_표식은_위치로_옮기고_본문에서는_뺀다():
    body = "\n".join(
        [
            "<!-- 1쪽 -->",
            "# 1장 개요",
            "개요 문단이다.",
            "<!-- 2쪽 --> 텍스트 없음",
            "<!-- 3쪽 -->",
            "## 1.1 목적",
            "목적 문단이다.",
        ]
    )
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "과업지시서.pdf", body)
    by_heading = {tuple(d.meta["headingPath"]): d for d in drafts}
    assert by_heading[("1장 개요",)].meta["page"] == 1
    assert by_heading[("1장 개요", "1.1 목적")].meta["page"] == 3
    for d in drafts:
        assert "<!--" not in d.content and "⟦" not in d.content
        assert "텍스트 없음" not in d.content


def test_한_조각이_여러_쪽에_걸치면_끝_쪽도_남긴다():
    body = "<!-- 4쪽 -->\n첫 문장이다.\n<!-- 5쪽 -->\n둘째 문장이다.\n<!-- 6쪽 -->\n셋째 문장이다."
    [draft] = chunking.chunk("DOCUMENT_UPLOAD", "보고서.pdf", body)
    assert draft.meta["page"] == 4 and draft.meta["pageEnd"] == 6
    assert draft.content == "첫 문장이다.\n둘째 문장이다.\n셋째 문장이다."


def test_쪽은_다음_조각으로_이어진다():
    # 3쪽에서 시작한 글이 길어 둘로 나뉘면 둘째 조각도 3쪽이다
    body = "<!-- 3쪽 -->\n" + " ".join(f"문장 {i} 이다." for i in range(600))
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "보고서.pdf", body)
    assert len(drafts) >= 2
    assert all(d.meta["page"] == 3 for d in drafts)
    assert all("pageEnd" not in d.meta for d in drafts)


def _sheet(rows: int) -> str:
    lines = ["## 시트: WBS", "", "| 행 | 작업 | 진척 |", "| --- | --- | --- |"]
    # 엑셀 2행부터. 5행은 비어 있어 건너뛴 것처럼 번호가 뛴다
    numbers = [n for n in range(2, 2 + rows + 1) if n != 5][:rows]
    detail = "가" * 40
    lines += [f"| {n} | 작업 {n} 상세 설명 문장이 길게 이어진다 {detail} | {n}% |" for n in numbers]
    return "\n".join(lines)


def test_엑셀_행_번호가_있는_표는_조각마다_행_범위를_남긴다():
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "WBS.xlsx", _sheet(60))
    assert len(drafts) >= 2, "표가 길면 여러 조각이어야 범위가 의미 있다"
    first = drafts[0]
    assert first.meta["headingPath"] == ["시트: WBS"]
    assert first.meta["rowStart"] == 2 and first.meta["rowEnd"] > 2
    # 조각 경계는 행 경계다. 행 가운데서 끊긴 줄이 없다
    for d in drafts:
        for line in d.content.split("\n"):
            if line.startswith("|"):
                assert line.endswith("|"), line
    # 범위는 이어진다(겹침은 허용). 번호가 뛴 5행은 어디에도 없다
    assert all("| 5 |" not in d.content for d in drafts)
    starts = [d.meta["rowStart"] for d in drafts]
    assert starts == sorted(starts)
    assert drafts[-1].meta["rowEnd"] == 2 + 60  # 5를 건너뛰어 끝 번호가 하나 밀린다


def test_행_번호_열이_없는_표에는_행_범위를_붙이지_않는다():
    body = "## 시트: 일정\n\n| 1 | 착수 |\n| --- | --- |\n| 2 | 분석 |\n| 3 | 설계 |"
    [draft] = chunking.chunk("DOCUMENT_UPLOAD", "일정.xlsx", body)
    assert "rowStart" not in draft.meta and "page" not in draft.meta
