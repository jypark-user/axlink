"""답변에 끼워 넣는 인포 템플릿 블록 (ARC-013).

블록 하나는 "이 자리에 이 그림을 그린다" 이다. 모델은 카탈로그에서 무엇을 그릴지(지표·차원·
템플릿, 또는 목록 종류와 상태)만 고르고, 값은 전부 서버가 만든다. 시맨틱 레이어의 집계이거나
표준 모델의 행이다(절대 규칙 1).

본문에는 `[그림 1]` 표식만 들어간다. 프런트가 그 자리에 위젯 렌더러를 끼운다. 표식이 없으면
답변 끝에 차례로 붙는다.
"""

import re
from dataclasses import dataclass

from app.rag.entity_table import EntityTable
from app.semantic.models import WidgetDataResponse

# 본문의 그림 자리. 각주 [1] 과 겹치지 않게 "그림" 을 넣는다.
MARKER = re.compile(r"\[그림\s*(\d{1,2})\]")


def marker_for(slot: int) -> str:
    return f"[그림 {slot}]"


@dataclass
class Block:
    """한 자리에 그릴 그림 하나."""

    slot: int  # 본문 표식 번호. 1부터
    template: str
    title: str
    data: WidgetDataResponse
    lines: list[str]  # 프롬프트 재료이자 수치 검문의 근거
    note: str | None = None  # 표·그림 아래 설명. 목록이면 범위 문장

    def as_event(self) -> dict:
        return {
            "slot": self.slot,
            "template": self.template,
            "title": self.title,
            "data": self.data.model_dump(),
            "note": self.note,
        }


def from_aggregate(slot: int, template: str, title: str, data: WidgetDataResponse,
                   lines: list[str]) -> Block:
    return Block(slot=slot, template=template, title=title, data=data, lines=lines)


def from_entity(slot: int, table: EntityTable) -> Block:
    """목록은 표로 그린다. 값도 상태 필터도 SQL 이 정한다."""
    return Block(
        slot=slot,
        template="DATA_TABLE",
        title=table.title,
        data=table.data,
        lines=table.lines,
        note=table.scope_line,
    )


# 프롬프트에 넣는 항목 수. 본문은 목록을 다시 나열하지 않으므로 성격을 알 만큼만 있으면 된다.
# 09.17 실측: 요구사항 41건을 통째로 넣으면 프롬프트가 불어나 모델이 시간 초과로 끊겼다.
PROMPT_ROWS = 8


def prompt_section(block: Block) -> str:
    """프롬프트에 넣는 블록 한 절. 본문이 이 자리에 표식을 놓게 번호를 앞세운다.

    항목은 앞부분만 넣는다. 전체는 그림이 들고 있고, 본문은 건수와 요점만 쓰기 때문이다.
    수치 검문의 근거는 잘리지 않은 block.lines 전체를 쓴다.
    """
    head = f"## 그림 {block.slot} ({block.title})"
    if block.note:
        head += f"\n{block.note}"
    shown = block.lines[:PROMPT_ROWS]
    body = "\n".join(shown)
    if len(block.lines) > len(shown):
        body += f"\n(나머지 {len(block.lines) - len(shown)}개는 그림에 있다. 본문에 옮기지 않는다.)"
    return head + "\n" + body


def placement_rule(blocks: list[Block]) -> str:
    """그림을 어디에 놓고 무엇을 쓰지 말지. 경량 모델은 예시를 그대로 베끼므로 표식만 남긴다."""
    names = "\n".join(f"- 그림 {b.slot}: {b.title}" for b in blocks)
    markers = ", ".join(marker_for(b.slot) for b in blocks)
    return (
        f"{names}\n"
        f"본문에서 그림을 보여 줄 자리에 {markers} 라고만 쓴다. 표식 뒤에 등호나 제목을 붙이지 "
        "않는다. 표식은 한 번씩만 쓰고 줄 하나를 차지하게 둔다.\n"
        "위 그림 절의 항목을 본문에 옮겨 적지 않는다. 목록을 문장으로 다시 나열하지 않는다. "
        "건수와 눈에 띄는 점만 한두 문장으로 말하고 나머지는 그림에 맡긴다."
    )


def used_slots(text: str) -> set[int]:
    return {int(m.group(1)) for m in MARKER.finditer(text)}


def append_missing(text: str, blocks: list[Block]) -> str:
    """본문이 표식을 안 쓴 그림은 끝에 붙인다. 만든 그림을 조용히 버리지 않는다."""
    used = used_slots(text)
    missing = [b for b in blocks if b.slot not in used]
    if not missing:
        return ""
    return "\n\n" + "\n".join(marker_for(b.slot) for b in missing)
