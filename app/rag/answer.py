"""답변 생성의 재료. 프롬프트 조립과 근거 부족 문안.

수치는 두 곳에서만 온다. 시맨틱 레이어의 집계 값과 근거 청크의 원문이다(QUR.RAG.002).
프롬프트로 그렇게 지시하고, 내보내기 전에 문장마다 검사한다(number_guard, ARC-017).
지시만으로는 경량 모델을 못 믿는다.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any

from app.common.korean import attach
from app.config import settings
from app.rag import blocks as blocks_mod
from app.rag import collection, vocab
from app.rag.routing import PreviousTurn, render_previous
from app.rag.search import RetrievedChunk
from app.semantic.models import WidgetDataResponse

SYSTEM_PROMPT = (
    "당신은 발주기관 담당자를 돕는 사업 관리 보조자다. 한국어로 간결하게 답한다.\n"
    "규칙:\n"
    "1. 수치는 '집계 값' 절에 제공된 값만 그대로 인용한다. 없는 수치는 만들지 않고, "
    "제공된 값을 더하거나 나누어 새 수치를 만들지도 않는다.\n"
    "1-1. 집계 값 절에 '산출 근거' 가 있으면 값을 말한 뒤 그 근거를 한 문장으로 덧붙인다. "
    "괄호의 분자·분모(예: 0건 / 41건)가 있으면 함께 말한다. 값이 0 이거나 없을 때는 그 이유가 "
    "근거에 있으면 반드시 말한다.\n"
    "2. 사실은 '근거' 절의 내용에서만 가져온다. 근거에 없는 내용은 모른다고 말한다.\n"
    "2-0. 항목의 지금 상태(진행중·종료 등)는 근거 머리의 '지금 상태'나 그림·목록의 상태 열을 "
    "따른다. 근거 원문(이슈 본문·"
    "회의록)에 적힌 계획·논의 문장으로 지금 상태를 말하지 않는다. 상태를 물으면 그 상태를 먼저 "
    "말한다.\n"
    "2-1. 근거가 예상·가정('~하면 ~할 수 있다', 리스크·대응 계획)이면 일어난 일로 쓰지 않는다. "
    "'리스크로 적힌 내용' 처럼 그 성격을 밝힌다.\n"
    "3. 근거를 인용한 문장 끝에 해당 근거 번호를 [1] 처럼 붙인다. 번호는 근거 절의 번호만 쓴다.\n"
    "4. 제목·목록 기호 없이 문단으로 답한다. 인사말과 사족은 넣지 않는다.\n"
    "4-1. '그림 놓기' 절이 있으면 그 지시대로 본문에 [그림 N] 표식만 놓는다. "
    "표식 자리에 표나 차트가 그려진다. 그림에 담긴 항목을 본문에 옮겨 적거나 다시 나열하지 "
    "않는다. 본문은 건수와 요점 한두 문장이면 된다.\n"
    '5. 출력은 {"answer": "<답변>"} 꼴의 JSON 객체 하나다. 생각 과정은 쓰지 않는다.\n'
    "6. '앞 대화' 절이 있으면 이번 질문의 '그 방법', '그거', '흐름' 은 앞 대화의 주제다. "
    "앞 답을 되풀이하지 말고 이번 질문이 새로 묻는 것만 답한다.\n"
    "6-1. 심각도 '미지정'은 수집한 도구의 이슈에 심각도가 없다는 뜻이다. "
    "낮은 위험이나 낮은 우선순위로 말하지 않고, "
    "필요하면 심각도가 지정되지 않았다고 그대로 말한다.\n"
    "7. 절차·방법의 흐름·단계·순서를 그림이나 도식으로 보여 달라는 질문에는 화면 그림을 "
    "그리지 않는다. 대신 산출 근거와 근거 절에 있는 절차를 '1) … → 2) … → 3) …' 처럼 한 줄에 "
    "한 단계씩 순서대로 쓴다. 이때는 규칙 4 의 문단 제한을 두지 않는다. 근거에 없는 단계를 "
    "지어내지 않는다.\n"
    "8. 진척률·비율은 %, 두 백분율의 차이는 %p 로 구분해 쓴다. 값에 붙은 기준일을 함께 말한다. "
    "'추정' 이라 적힌 값(계획 진척률)은 추정이라고 밝힌다. 줄에 '비교할 수 없음', '값을 씀' "
    "같은 단서가 있으면 그대로 전한다."
)

# 생성 출력을 이 모양으로 묶는다. 경량 모델이 답 앞에 생각을 늘어놓는 길을 막는다.
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
_ANSWER_KEY = '"answer"'
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "/": "/", "\\": "\\", '"': '"'}

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
            # 상태·심각도 코드는 화면과 같은 발주기관 어휘로(IN_PROGRESS → 진행중)
            value = row.values.get(f"{col.key}_label") or vocab.word(row.values.get(col.key))
            if value is not None:
                labels.append(f"{col.label} {value}")
        head = ", ".join(labels) if labels else data.measureLabel
        line = f"- {head}: {format_value(row.values.get('value'))}{unit}"
        num, den = row.values.get("numerator"), row.values.get("denominator")
        if num is not None and den is not None:
            line += f" ({format_value(num)}건 / {format_value(den)}건)"
        lines.append(line)
    # 전체 줄에도 지표 이름을 붙인다. "전체" 만 있으면 수치 검문의 라벨 짝짓기에서 "일반 이슈는
    # 9건" 의 9 가 지표 이름을 가진 범주 줄(일반 이슈 상태 …)에 밀려 막혔다(UC-060-S02 실모델)
    if data.total is not None and data.dimensions:
        total = format_value(data.total.values.get("value"))
        lines.append(f"- {data.measureLabel} 전체: {total}{unit}")
    elif data.dimensions and unit == "건" and not data.truncated:
        # 건수는 나눈 값을 더하면 전체다. 서버가 더해 준다. 모델이 더하면 수치 검문에 막힌다
        # (10-07 "이슈가 몇 건이야?" 가 상태별 7·5 를 받아 12 를 만들어 막혔다)
        values = [row.values.get("value") for row in data.rows]
        if values and all(isinstance(v, int | float) for v in values):
            lines.append(f"- {data.measureLabel} 전체(항목 합): {format_value(sum(values))}{unit}")
    # 나눈 항목이 몇 개인지(11-20). 비율 지표는 더한 전체가 없어 모델이 「진행 중인 작업은 17개」를
    # 세어 쓰면 근거 없는 값으로 막혔다. 잘린 목록은 전체 수를 모르니 적지 않는다
    if len(dim_cols) == 1 and data.rows and not data.truncated and unit != "건":
        lines.append(f"- {dim_cols[0].label} 수: {len(data.rows)}개")
    if data.previousTotal is not None:
        previous = format_value(data.previousTotal.values.get("value"))
        lines.append(f"- 직전 구간 전체: {previous}{unit}")
    if data.target is not None:
        lines.append(f"- 목표: {format_value(data.target)}{unit}")
    if not lines:
        lines.append(f"- {data.measureLabel}: 집계된 값이 없음")
    if data.basis:
        # 왜 그 숫자인지. 모델은 이 문장을 근거로 값의 뜻을 풀어 말할 수 있다
        lines.append(f"- 산출 근거: {data.basis}")
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
    previous: list[PreviousTurn] | None = None,
    values: tuple[str, list[str]] | None = None,
) -> str:
    """values 는 그림 없이 줄로만 주는 값(일정 질문의 기간 비교 등). 집계 값과 같은 규칙이다."""
    parts = [f"## 질문\n{question}"]
    if previous:
        parts.append("## 앞 대화 (마지막이 직전)\n" + render_previous(previous))
    if listing:
        parts.append("## 목록 범위\n" + listing)
    if aggregate is not None:
        scope = len(aggregate.data.appliedProjectIds)
        stamp = aggregate.data.generatedAt[:10]
        head = f"## 집계 값 ({aggregate.title}, 사업 {scope}개 범위, 기준 {stamp})"
        parts.append(head + "\n" + "\n".join(aggregate.lines))
    if values is not None:
        parts.append(f"## 집계 값 ({values[0]})\n" + "\n".join(values[1]))
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
    # 이슈는 지금 상태를 머리에 둔다. 본문의 계획 문장을 지금 상태로 읽지 않게(UC-060-S16)
    state = f" · 지금 상태 {chunk.status}" if chunk.status else ""
    return f"[{no}] {chunk.source_title}{where}{state}\n{chunk.content.strip()}"


def focus_rows(chunk: RetrievedChunk, query: str) -> RetrievedChunk:
    """XLSX 표 조각에서 질문 낱말이 맞는 행만 남긴다. 위치도 그 행으로 좁힌다(AC-060-11).

    시트 하나가 조각 하나로 들어가면 출처가 「2~7행」이 되고 앞부분만 보여 정작 답인 행이
    잘린다. 맞는 행이 없거나 모든 행이 맞으면 조각을 그대로 둔다. 값은 원문 줄 그대로다.
    """
    if chunk.row_start is None:
        return chunk
    words = [w.lower() for w in query.split() if len(w) >= 2]
    if not words:
        return chunk
    lines = chunk.content.split("\n")
    rows: list[tuple[int, str, int]] = []
    head: list[str] = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells and cells[0].isdigit():
            hits = sum(1 for w in words if any(w in c.lower() for c in cells[1:]))
            rows.append((int(cells[0]), line, hits))
        else:
            head.append(line)
    best = max((h for _, _, h in rows), default=0)
    picked = [(n, line) for n, line, h in rows if best and h == best]
    if not picked or len(picked) == len(rows):
        return chunk
    numbers = [n for n, _ in picked]
    return replace(
        chunk,
        content="\n".join([*head, *(line for _, line in picked)]),
        row_start=min(numbers),
        row_end=max(numbers),
    )


def location_label(chunk: RetrievedChunk) -> str:
    """원문 위치를 사람이 읽는 꼴로, 괄호에 싸서. 프롬프트 근거 머리에 붙는다."""
    text = location_text(chunk)
    return f" ({text})" if text else ""


def location_text(chunk: RetrievedChunk) -> str | None:
    """원문 위치(SWFR.RAG.003). 표제 경로, 쪽(걸치면 범위), XLSX 행 범위 순으로 잇는다.

    HWP·HWPX 는 쪽이 없어 문단 순번과 표·행 번호를 잇는다(DEC-21). 예: 「문단 3~4 / 표 1 · 2행」.
    """
    bits = []
    if chunk.heading_path:
        bits.append(" > ".join(chunk.heading_path))
    if chunk.page_no is not None:
        bits.append(_span("p.", chunk.page_no, chunk.page_end, ""))
    if chunk.row_start is not None:
        bits.append(_span("", chunk.row_start, chunk.row_end, "행"))
    if chunk.para_start is not None:
        bits.append(_span("문단 ", chunk.para_start, chunk.para_end, ""))
    if chunk.table_no is not None:
        table = _span("표 ", chunk.table_no, chunk.table_end, "")
        if chunk.table_row_start is not None:
            table += " · " + _span("", chunk.table_row_start, chunk.table_row_end, "행")
        bits.append(table)
    return " / ".join(bits) if bits else None


def _span(prefix: str, start: int, end: int | None, suffix: str) -> str:
    if end is not None and end != start:
        return f"{prefix}{start}~{end}{suffix}"
    return f"{prefix}{start}{suffix}"


def snippet(chunk: RetrievedChunk, limit: int | None = None) -> str:
    """출처 카드에 보이는 원문 조각. 위치 표시를 앞에 붙여 어느 절인지 바로 보이게 한다."""
    cap = settings.rag_snippet_chars if limit is None else limit
    body = " ".join(chunk.content.split())
    if len(body) > cap:
        body = body[:cap].rstrip() + "…"
    where = location_label(chunk)
    return f"{where.strip(' ()')}\n{body}" if where else body


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


def off_topic() -> str:
    return (
        "이 도우미는 사업의 진척·이슈·요구사항·산출물·리스크와 관련 문서에 대해서만 답합니다. "
        "사업과 관련된 질문으로 바꿔 보십시오."
    )


# 모델을 부르지 않고 서버가 쓰는 답. 이유를 하나로 뭉치지 않는다. 조회 오류를 데이터 없음으로
# 말하지 않는다(SWFR.RAG.007).


def no_documents() -> str:
    return (
        "선택한 사업 범위에 올라온 문서·이슈가 아직 없어 문서 내용으로는 답할 수 없습니다. "
        "문서를 올리거나 도구 연동으로 수집하면 답할 수 있습니다."
    )


def no_relevant_documents(max_similarity: float) -> str:
    return (
        "올라온 문서·이슈에서 이 질문과 맞는 내용을 찾지 못해 답변을 만들지 않았습니다. "
        f"(최고 유사도 {max_similarity:.2f}, 기준 {settings.rag_min_similarity:.2f}) "
        "질문을 더 구체적으로 적어 보십시오."
    )


def no_collected_data(label: str, state: str) -> str:
    """건수를 셀 자료를 아직 믿을 수 없을 때. 0건이라고 말하지 않는다(GH-127)."""
    subject = attach(label, "을")
    if state == collection.NOT_CONNECTED:
        return (
            f"선택한 사업에 연동한 도구가 없어 {subject} 셀 자료를 수집하지 않았습니다. "
            "0건이라는 뜻은 아닙니다. 도구를 연동하고 수집하면 답할 수 있습니다."
        )
    if state == collection.COLLECT_FAILED:
        return (
            f"마지막 수집이 실패해 {subject} 믿고 셀 수 없습니다. 0건이라는 뜻은 아닙니다. "
            "동기화 화면에서 실패 이유를 확인해 주십시오."
        )
    return (
        f"도구는 연동돼 있지만 아직 수집이 끝나지 않아 {subject} 셀 수 없습니다. "
        "첫 수집이 끝나면 답할 수 있습니다."
    )


def no_measure_data(label: str, basis: str | None) -> str:
    text = f"{label} 값이 아직 없어 답할 수 없습니다."
    if basis:
        text += f" 이 값은 이렇게 산출합니다. {basis}"
    return text


def no_overview_data() -> str:
    return (
        "선택한 사업 범위에 진척·이슈·산출물·리스크 값이 아직 없어 현황을 요약할 수 없습니다. "
        "도구 연동으로 수집하면 답할 수 있습니다."
    )


def model_down_values(title: str, lines: list[str]) -> str:
    """모델 서버를 쓸 수 없을 때 집계 값만으로 내는 답(AC-060-9, DEF-V041). 문장은 서버가 쓴다."""
    body = "\n".join(lines)
    return (
        "AI 모델 서버를 지금 쓸 수 없어 문장 답 대신 집계 값을 그대로 보여 드립니다.\n\n"
        f"**{title}**\n{body}"
    )


def unsupported() -> str:
    return "이 질문에 맞는 조회 항목이 아직 없어 답하지 못했습니다."


def search_disabled() -> str:
    return (
        "지금은 문서 검색이 멈춰 있어 문서 근거로 답하지 못했습니다. 검색 모델과 색인이 맞지 "
        "않습니다. 관리자가 설정의 검색 모델 영역에서 원인을 볼 수 있습니다."
    )


def query_error() -> str:
    return (
        "조회 중 오류가 나서 답하지 못했습니다. 값이 없다는 뜻은 아닙니다. "
        "잠시 뒤 다시 시도해 주십시오."
    )


def clarify() -> str:
    return "질문을 어느 쪽으로 볼지 정하기 어렵습니다. 아래에서 보려는 것을 골라 주십시오."


def no_delay_reason() -> str:
    return (
        "지연 사유를 적은 문서·이슈는 찾지 못했습니다. 위 내용은 계획보다 늦은 작업까지만 "
        "확인한 것입니다."
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
