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
