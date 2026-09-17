"""답변 생성의 재료. 프롬프트 조립, 수치 검문, 근거 부족 문안.

수치는 두 곳에서만 온다. 시맨틱 레이어의 집계 값과 근거 청크의 원문이다(QUR.RAG.002).
프롬프트로 그렇게 지시하고, 생성이 끝난 뒤 답변의 숫자를 그 두 곳과 대조한다.
지시만으로는 경량 모델을 못 믿는다.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.rag import blocks as blocks_mod
from app.rag.search import RetrievedChunk
from app.semantic.models import WidgetDataResponse

SYSTEM_PROMPT = (
    "당신은 발주기관 담당자를 돕는 사업 관리 보조자다. 한국어로 간결하게 답한다.\n"
    "규칙:\n"
    "1. 수치는 '집계 값' 절에 제공된 값만 그대로 인용한다. 없는 수치는 만들지 않고, "
    "제공된 값을 더하거나 나누어 새 수치를 만들지도 않는다.\n"
    "2. 사실은 '근거' 절의 내용에서만 가져온다. 근거에 없는 내용은 모른다고 말한다.\n"
    "3. 근거를 인용한 문장 끝에 해당 근거 번호를 [1] 처럼 붙인다. 번호는 근거 절의 번호만 쓴다.\n"
    "4. 제목·목록 기호 없이 문단으로 답한다. 인사말과 사족은 넣지 않는다.\n"
    "4-1. '그림 놓기' 절이 있으면 그 지시대로 본문에 [그림 N] 표식만 놓는다. "
    "표식 자리에 표나 차트가 그려진다. 그림에 담긴 항목을 본문에 옮겨 적거나 다시 나열하지 "
    "않는다. 본문은 건수와 요점 한두 문장이면 된다.\n"
    '5. 출력은 {"answer": "<답변>"} 꼴의 JSON 객체 하나다. 생각 과정은 쓰지 않는다.'
)

# 생성 출력을 이 모양으로 묶는다. 경량 모델이 답 앞에 생각을 늘어놓는 길을 막는다.
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
_ANSWER_KEY = '"answer"'
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "/": "/", "\\": "\\", '"': '"'}

_FOOTNOTE = re.compile(r"\[\d{1,2}\]")
_DATE = re.compile(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{4}년|\d{1,2}월|\d{1,2}일")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


@dataclass
class AggregateContext:
    """집계 경로가 프롬프트에 넣는 값. 문장으로 펼친 줄과 검문용 숫자 목록을 같이 든다."""

    title: str
    data: WidgetDataResponse
    lines: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, title: str, data: WidgetDataResponse) -> "AggregateContext":
        return cls(title=title, data=data, lines=aggregate_lines(data))


def aggregate_lines(data: WidgetDataResponse) -> list[str]:
    """집계 응답을 한 줄씩 문장 재료로 편다. 값의 표기(소수 자리)는 여기서 정해지고,
    검문은 같은 표기를 기준으로 하므로 모델이 이 줄을 베끼면 통과한다."""
    unit = data.unit or ""
    dim_cols = [c for c in data.columns if c.key != "value"]
    lines: list[str] = []
    for row in data.rows:
        labels = []
        for col in dim_cols:
            if col.key.endswith("_label"):
                continue
            value = row.values.get(f"{col.key}_label") or row.values.get(col.key)
            if value is not None:
                labels.append(f"{col.label} {value}")
        head = ", ".join(labels) if labels else data.measureLabel
        lines.append(f"- {head}: {format_value(row.values.get('value'))}{unit}")
    if data.total is not None and data.dimensions:
        lines.append(f"- 전체: {format_value(data.total.values.get('value'))}{unit}")
    if data.previousTotal is not None:
        previous = format_value(data.previousTotal.values.get("value"))
        lines.append(f"- 직전 구간 전체: {previous}{unit}")
    if data.target is not None:
        lines.append(f"- 목표: {format_value(data.target)}{unit}")
    if not lines:
        lines.append(f"- {data.measureLabel}: 집계된 값이 없음")
    return lines


def format_value(value: object) -> str:
    if value is None:
        return "값 없음"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    return str(value)


def user_prompt(
    question: str,
    chunks: list[RetrievedChunk],
    aggregate: AggregateContext | None,
    listing: str | None = None,
    blocks: list["blocks_mod.Block"] | None = None,
) -> str:
    parts = [f"## 질문\n{question}"]
    if listing:
        parts.append("## 목록 범위\n" + listing)
    if aggregate is not None:
        scope = len(aggregate.data.appliedProjectIds)
        stamp = aggregate.data.generatedAt[:10]
        head = f"## 집계 값 ({aggregate.title}, 사업 {scope}개 범위, 기준 {stamp})"
        parts.append(head + "\n" + "\n".join(aggregate.lines))
    for block in blocks or []:
        parts.append(blocks_mod.prompt_section(block))
    if blocks:
        parts.append("## 그림 놓기\n" + blocks_mod.placement_rule(blocks))
    if chunks:
        parts.append("## 근거\n" + "\n\n".join(_evidence(i, c) for i, c in enumerate(chunks, 1)))
    else:
        parts.append("## 근거\n(없음. 집계 값만으로 답한다.)")
    return "\n\n".join(parts)


def _evidence(no: int, chunk: RetrievedChunk) -> str:
    where = location_label(chunk)
    return f"[{no}] {chunk.source_title}{where}\n{chunk.content.strip()}"


def location_label(chunk: RetrievedChunk) -> str:
    """원문 위치를 사람이 읽는 꼴로. 표제 경로가 있으면 그것, 페이지가 있으면 페이지."""
    bits = []
    if chunk.heading_path:
        bits.append(" > ".join(chunk.heading_path))
    if chunk.page_no is not None:
        bits.append(f"p.{chunk.page_no}")
    return f" ({' / '.join(bits)})" if bits else ""


def snippet(chunk: RetrievedChunk, limit: int | None = None) -> str:
    """출처 카드에 보이는 원문 조각. 위치 표시를 앞에 붙여 어느 절인지 바로 보이게 한다."""
    cap = settings.rag_snippet_chars if limit is None else limit
    body = " ".join(chunk.content.split())
    if len(body) > cap:
        body = body[:cap].rstrip() + "…"
    where = location_label(chunk)
    return f"{where.strip(' ()')}\n{body}" if where else body


# ---------------------------------------------------------------- 수치 검문


def numbers_in(text: str) -> set[str]:
    """본문의 숫자를 정규화한 문자열 집합으로. 각주 번호·그림 표식·날짜는 수치가 아니라 뺀다."""
    body = blocks_mod.MARKER.sub(" ", text)
    body = _FOOTNOTE.sub(" ", body)
    body = _DATE.sub(" ", body)
    found: set[str] = set()
    for m in _NUMBER.finditer(body):
        found.add(_normalize(m.group(0)))
    return found


def _normalize(token: str) -> str:
    plain = token.replace(",", "")
    try:
        value = float(plain)
    except ValueError:
        return plain
    return str(int(value)) if value.is_integer() else f"{value:g}"


def ungrounded_numbers(answer: str, grounds: list[str]) -> list[str]:
    """답변에는 있는데 집계 값·근거 원문·질문 어디에도 없는 숫자."""
    allowed: set[str] = set()
    for ground in grounds:
        allowed |= numbers_in(ground)
    return sorted(numbers_in(answer) - allowed, key=_sort_key)


def _sort_key(token: str) -> tuple[float, str]:
    try:
        return (float(token), token)
    except ValueError:
        return (float("inf"), token)


def guard_note(numbers: list[str]) -> str:
    return (
        "\n\n※ 위 답변의 수치 " + ", ".join(numbers)
        + " 은(는) 집계 값과 근거 원문에 없는 값입니다. 화면의 집계 값을 기준으로 보십시오."
    )


# ---------------------------------------------------------------- 문안


def listing_scope(label: str, shown: int, total: int) -> str:
    """목록 질문의 근거가 전체인지 일부인지. 이 줄의 숫자는 근거로 친다."""
    if shown >= total:
        return f"사업 범위 안의 {label} 전체 {total}건이 아래 근거다. 빠짐없이 나열해도 된다."
    return (
        f"사업 범위 안의 {label}은 총 {total}건이고 그중 앞 {shown}건만 아래 근거다. "
        "나머지는 모른다고 한다."
    )


def empty_listing(label: str) -> str:
    return (
        f"사업 범위 안에 색인된 {label}이(가) 없어 답변을 만들지 않았습니다. "
        "수집이나 사업 범위를 확인해 보십시오."
    )


def insufficient_evidence(max_similarity: float, candidate_count: int) -> str:
    if candidate_count == 0:
        return (
            "선택한 사업 범위에 색인된 문서·이슈가 없어 답할 근거가 없습니다. "
            "문서를 올리거나 도구 연동으로 수집한 뒤 다시 질문해 주십시오."
        )
    return (
        "질문과 충분히 가까운 근거를 찾지 못해 답변을 만들지 않았습니다. "
        f"(최고 유사도 {max_similarity:.2f}, 기준 {settings.rag_min_similarity:.2f}) "
        "질문을 더 구체적으로 적거나 사업 범위를 바꿔 보십시오."
    )


def strip_think(pieces: Iterator[str]) -> Iterator[str]:
    """스트림 조각에서 <think>…</think> 를 걷어낸다. think 를 꺼도 모델에 따라 섞여 나온다."""
    buffer = ""
    inside = False
    for piece in pieces:
        buffer += piece
        while buffer:
            if inside:
                end = buffer.find(_THINK_CLOSE)
                if end < 0:
                    buffer = buffer[-len(_THINK_CLOSE) :]
                    break
                buffer = buffer[end + len(_THINK_CLOSE) :]
                inside = False
                continue
            start = buffer.find(_THINK_OPEN)
            if start >= 0:
                if start:
                    yield buffer[:start]
                buffer = buffer[start + len(_THINK_OPEN) :]
                inside = True
                continue
            # 여는 태그가 잘려 들어오는 중일 수 있다. 태그 길이만큼은 들고 있는다.
            keep = _partial_tag_length(buffer)
            if len(buffer) > keep:
                yield buffer[: len(buffer) - keep]
                buffer = buffer[len(buffer) - keep :]
            break
    if buffer and not inside:
        yield buffer


def _partial_tag_length(text: str) -> int:
    for n in range(min(len(text), len(_THINK_OPEN) - 1), 0, -1):
        if _THINK_OPEN.startswith(text[-n:]):
            return n
    return 0


# ---------------------------------------------------------------- JSON 답변 풀기


def decode_answer(pieces: Iterator[str]) -> Iterator[str]:
    """{"answer": "..."} 조각을 받아 문자열 값만 흘린다. 출력을 JSON 으로 묶은 대가로
    조각마다 이스케이프를 풀어야 하고, 이스케이프가 조각 경계에 걸리면 다음 조각을 기다린다."""
    decoder = _AnswerDecoder()
    for piece in pieces:
        text = decoder.feed(piece)
        if text:
            yield text
    tail = decoder.finish()
    if tail:
        yield tail


class _AnswerDecoder:
    def __init__(self) -> None:
        self._buf = ""
        self._phase = 0  # 0 값의 여는 따옴표 찾는 중, 1 값 본문, 2 끝

    def feed(self, piece: str) -> str:
        self._buf += piece
        if self._phase == 0:
            at = self._buf.find(_ANSWER_KEY)
            if at < 0:
                return ""
            rest = self._buf[at + len(_ANSWER_KEY) :]
            quote = rest.find('"')
            if quote < 0:
                return ""
            self._buf = rest[quote + 1 :]
            self._phase = 1
        return self._drain() if self._phase == 1 else ""

    def _drain(self) -> str:
        buf = self._buf
        out: list[str] = []
        i = 0
        while i < len(buf):
            ch = buf[i]
            if ch == '"':
                self._phase = 2
                self._buf = ""
                return "".join(out)
            if ch != "\\":
                out.append(ch)
                i += 1
                continue
            if i + 1 >= len(buf):
                break  # 이스케이프가 잘려 들어왔다. 다음 조각과 이어 본다
            nxt = buf[i + 1]
            if nxt != "u":
                out.append(_ESCAPES.get(nxt, nxt))
                i += 2
                continue
            if i + 6 > len(buf):
                break
            code = int(buf[i + 2 : i + 6], 16)
            if 0xD800 <= code <= 0xDBFF:  # 서러게이트 쌍은 12자가 다 와야 한다
                if i + 12 > len(buf):
                    break
                low = int(buf[i + 8 : i + 12], 16)
                out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                i += 12
                continue
            out.append(chr(code))
            i += 6
        self._buf = buf[i:]
        return "".join(out)

    def finish(self) -> str:
        """닫는 따옴표 없이 끝났으면(중단·형식 이탈) 남은 것을 그대로 준다."""
        rest, self._buf = self._buf, ""
        if self._phase == 1:
            return rest
        if self._phase == 0 and rest.strip():
            try:
                parsed = json.loads(rest)
            except json.JSONDecodeError:
                return rest.strip()
            if isinstance(parsed, dict):
                return str(next((v for v in parsed.values() if isinstance(v, str)), ""))
            return rest.strip()
        return ""
