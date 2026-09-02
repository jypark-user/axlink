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


def test_oversized_single_sentence_is_cut():
    """표나 URL 덩어리처럼 문장 경계가 없는 입력도 최대치를 넘기지 않는다."""
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "표", "가" * 20000)
    assert len(drafts) > 1
    for draft in drafts:
        assert draft.token_count <= settings.chunk_max_tokens


def test_date_line_is_not_a_heading():
    drafts = chunking.chunk("DOCUMENT_UPLOAD", "회의록", "2026. 8. 29 회의를 열었다.\n논의했다.")
    assert all(d.meta["headingPath"] == [] for d in drafts)
