"""청킹. 파일럿 설계 03-physical-backend §6.1 의 파라미터를 그대로 쓴다.

토큰은 세지 않고 추정한다(chars / 2.4). 토크나이저를 의존성으로 들이면 모델을 바꿀 때마다
청킹 결과가 흔들리는데, 청크 경계는 근사로 충분하다.

표제 경로를 meta 에 남기는 게 이 모듈의 존재 이유다 — 답변에 원문 위치를 붙여야 한다
(SWFR.RAG.003 · SWFR.RAG.006).
"""

import math
import re
from dataclasses import dataclass, field

from app.config import settings

# 제목+본문 조합으로 1청크가 되는 소스들. 짧고 단위가 분명해서 쪼갤 이유가 없다.
SINGLE_CHUNK_SOURCES = frozenset(
    {
        "REQUIREMENT",
        "ISSUE",
        "RISK",
        "CHANGE_REQUEST",
        "CORRECTION_ACTION",
        "PROGRESS_RECORD",
    }
)

_CHARS_PER_TOKEN = 2.4
_MAX_HEADING_DEPTH = 6

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_KOREAN_HEADING = re.compile(r"^(제\s*\d+\s*([장절]))\s*(.*)$")
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?。])\s+|\n{2,}")

# "1." "가." "비고  1." 처럼 항목 번호로 끝나는 조각. 공문서는 본문에도 번호를 다는데,
# 그 마침표에서 끊으면 원문 한 줄이 파편으로 흩어진다. 정규식에 예외를 계속 붙이는
# 대신, 끊긴 뒤 되붙이는 규칙 하나로 처리한다.
#
# 번호 앞이 공백이거나 줄 시작이어야 한다 — 이 조건이 "…한다." 같은 정상 종결을 지킨다
# ("다" 앞은 "한" 이라 걸리지 않는다).
_TRAILING_LABEL = re.compile(r"(?:^|\s)(?:\d+|[가-힣]|[a-zA-Z]|[ivxIVX]+)\.$")

# 목차 줄 — "3. 계약사항 <탭> <마커> <탭> 44" 꼴로 페이지 번호가 끝에 붙는다.
# 본문에 같은 제목이 다시 나오므로 목차를 표제로 삼으면 경로가 둘로 갈리고,
# 제목 한 줄짜리 빈 청크가 생겨 검색에서 정작 답이 있는 본문을 밀어낸다.
_TOC_LINE = re.compile(r"[\t.·…]\s*\d{1,4}$")

# 공문서는 본문에도 번호를 단다. 명사형·종결형으로 끝나면 표제가 아니라 문장으로 본다.
_SENTENCE_TAIL = (".", "다", "요", "함", "음", "됨", "임")
_MAX_HEADING_CHARS = 60


@dataclass
class ChunkDraft:
    chunk_index: int
    content: str
    token_count: int
    meta: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def chunk(source_type: str, title: str, body: str | None) -> list[ChunkDraft]:
    """소스 하나를 청크 목록으로 만든다. 빈 본문이면 제목만으로 1청크."""
    text = (body or "").strip()
    title = (title or "").strip()

    if source_type in SINGLE_CHUNK_SOURCES:
        joined = f"{title}\n\n{text}".strip() if title else text
        if not joined:
            return []
        if estimate_tokens(joined) <= settings.chunk_max_tokens:
            return [ChunkDraft(0, joined, estimate_tokens(joined), {"headingPath": []})]
        sections = [([], joined)]
    else:
        if not text:
            if not title:
                return []
            return [ChunkDraft(0, title, estimate_tokens(title), {"headingPath": []})]
        sections = _split_sections(text)

    drafts: list[ChunkDraft] = []
    for heading_path, section_text in sections:
        for content in _pack(section_text):
            drafts.append(
                ChunkDraft(
                    chunk_index=len(drafts),
                    content=content,
                    token_count=estimate_tokens(content),
                    meta={"headingPath": heading_path},
                )
            )
    return drafts


def _split_sections(text: str) -> list[tuple[list[str], str]]:
    """표제 기준 1단계 분할. 표제를 만나면 경로를 갱신하고 새 구획을 연다."""
    sections: list[tuple[list[str], str]] = []
    path: list[str] = []
    buffer: list[str] = []

    def flush(current_path: list[str]) -> None:
        content = "\n".join(buffer).strip()
        if content:
            sections.append((list(current_path), content))
        buffer.clear()

    for line in text.splitlines():
        parsed = _parse_heading(line)
        if parsed is None:
            buffer.append(line)
            continue
        level, heading = parsed
        flush(path)
        path = path[: level - 1] + [heading]
        path = path[:_MAX_HEADING_DEPTH]
        buffer.append(heading)  # 표제도 본문에 남긴다 — 청크만 봐도 무엇에 관한 글인지 알게

    flush(path)
    return sections or [([], text)]


def _parse_heading(line: str) -> tuple[int, str] | None:
    stripped = line.strip()
    if not stripped or _TOC_LINE.search(stripped):
        return None

    md = _MARKDOWN_HEADING.match(stripped)
    if md:
        return len(md.group(1)), md.group(2)

    kr = _KOREAN_HEADING.match(stripped)
    if kr:
        level = 1 if kr.group(2) == "장" else 2
        return level, stripped

    num = _NUMBERED_HEADING.match(stripped)
    # "1. 개요" 는 표제지만 "2026. 8. 29 회의" 나 "1. … 부과함" 은 표제가 아니다.
    if num and len(stripped) <= _MAX_HEADING_CHARS and not stripped.endswith(_SENTENCE_TAIL):
        return num.group(1).count(".") + 1, stripped

    return None


def _pack(text: str) -> list[str]:
    """문장 단위 그리디 패킹 + 오버랩. 문장 경계에서만 끊는다."""
    target = settings.chunk_target_tokens
    maximum = settings.chunk_max_tokens
    minimum = settings.chunk_min_tokens
    overlap = int(target * settings.chunk_overlap_ratio)

    sentences = _rejoin_labels(
        [s.strip() for s in _SENTENCE_BREAK.split(text) if s and s.strip()]
    )
    if not sentences:
        return []

    chunks: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        tokens = estimate_tokens(sentence)
        if tokens > maximum:
            # 문장 하나가 최대치를 넘는 경우(표·URL 덩어리). 어쩔 수 없이 길이로 자른다.
            if current:
                chunks.append(current)
                current, current_tokens = [], 0
            chunks.extend([piece] for piece in _split_oversized(sentence, target))
            continue
        if current and current_tokens + tokens > target:
            chunks.append(current)
            current = _overlap_tail(current, overlap)
            current_tokens = sum(estimate_tokens(s) for s in current)
            if current_tokens + tokens > maximum:
                # 꼬리 문장이 커서 오버랩만으로 최대치를 넘길 판이면 꼬리를 버린다.
                # 문맥을 조금 잃더라도 청크 크기 계약이 먼저다 — 임베딩 품질이 걸려 있다.
                current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += tokens

    if current:
        chunks.append(current)

    return _merge_short_tail(chunks, minimum, maximum)


def _rejoin_labels(sentences: list[str]) -> list[str]:
    """번호만 남은 조각을 다음 문장에 되붙인다.

    "비고  1. 소프트웨어기술자란 …" 이 "비고  1." 과 "소프트웨어기술자란 …" 으로
    갈리면 원문 한 줄이 파편이 된다. 검색에서도 "1." 만 든 조각은 쓸모가 없다.
    """
    out: list[str] = []
    pending = ""
    for sentence in sentences:
        if _TRAILING_LABEL.search(sentence):
            pending = f"{pending} {sentence}" if pending else sentence
            continue
        out.append(f"{pending} {sentence}" if pending else sentence)
        pending = ""
    if pending:
        out.append(pending)
    return out


def _overlap_tail(sentences: list[str], overlap_tokens: int) -> list[str]:
    """앞 청크의 꼬리 문장들을 다음 청크 머리에 복제한다. 전부 복제하지는 않는다."""
    tail: list[str] = []
    total = 0
    for sentence in reversed(sentences[:-1] if len(sentences) > 1 else sentences):
        tail.insert(0, sentence)
        total += estimate_tokens(sentence)
        if total >= overlap_tokens:
            break
    return tail


def _split_oversized(sentence: str, target_tokens: int) -> list[str]:
    size = max(1, int(target_tokens * _CHARS_PER_TOKEN))
    return [sentence[i : i + size] for i in range(0, len(sentence), size)]


def _merge_short_tail(chunks: list[list[str]], minimum: int, maximum: int) -> list[str]:
    """최소치 미만 조각은 직전 청크에 붙인다. 최대치를 넘기면서까지 붙이지는 않는다."""
    texts = ["\n".join(c) for c in chunks]
    merged: list[str] = []
    for text in texts:
        if (
            merged
            and estimate_tokens(text) < minimum
            and estimate_tokens(merged[-1]) + estimate_tokens(text) <= maximum
        ):
            merged[-1] = merged[-1] + "\n" + text
        else:
            merged.append(text)
    return merged
