"""「이번 달 마일스톤 현황은?」 (착수보고 대표 질의 진척·일정).

모델은 이 질문을 일정 준수율 지표로 골랐다. 준수율은 기한이 지난 마일스톤만 세는 비율이라
기한 전인 마일스톤밖에 없는 달에는 값이 없고, 값이 있어도 「현황」이 아니다(11-23 실측). 그래서
마일스톤을 묻는 질문은 마일스톤 한 줄씩의 표로 답한다. 기한 안 닫힘 판정은 일정 준수율과 같은
조건이다(마지막으로 닫힌 날의 사업 시간대 날짜 ≤ 기한).
"""

import re
from datetime import date, timedelta
from typing import Any

from app.db import fetch_all
from app.rag import intents
from app.rag.blocks import Block
from app.rag.question_period import ActivityRange, activity_range
from app.semantic.models import WidgetRow

_ASKS = re.compile(r"마일스톤|마일 스톤|milestone", re.IGNORECASE)
# 비율을 물으면 지표 경로가 답한다
_RATE = re.compile(r"준수율|준수 율|비율|몇\s*%|퍼센트")

NO_MILESTONES = (
    "이 사업의 도구에 마일스톤(GitHub 마일스톤·Redmine 버전)이 없습니다. "
    "WBS 일정은 「지연 작업」이나 「계획 대비 실적」으로 물어볼 수 있습니다."
)


def asks(question: str) -> bool:
    return bool(_ASKS.search(question)) and not _RATE.search(question)


def _state(row: dict[str, Any], today: date) -> str:
    due, closed = row["due_on"], row["closed_day"]
    if row["state"] == "CLOSED":
        if due is None or closed is None:
            return "닫힘"
        return "기한 안 닫힘" if closed <= due else "늦게 닫힘"
    if due is None:
        return "열림(기한 없음)"
    return "기한 지남" if due < today else "진행 중"


def build(
    cur: Any, question: str, project_ids: list[str], slot: int, today: date | None = None
) -> tuple[Block | None, str | None]:
    """(표, 서버 문안). 마일스톤이 아예 없거나 그 기간에 없으면 표 없이 문안만 준다."""
    today = today or intents.today()
    period: ActivityRange | None = activity_range(question, today)
    if period is not None and period.start == today.replace(day=1) and period.end == today:
        # 이번 달 마일스톤은 이달 말 기한까지 본다. 활동 기간(오늘까지)과 다르다
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        period = ActivityRange(period.start, nxt - timedelta(days=1))
    rows = fetch_all(
        cur,
        """
        select m.title, m.due_on, m.state, p.name as project_name,
               (m.closed_at at time zone 'Asia/Seoul')::date as closed_day,
               count(i.id) as issues,
               count(i.id) filter (where i.status in ('RESOLVED', 'CLOSED')) as done
          from milestone m
          join project p on p.id = m.project_id
          left join issue i on i.milestone_id = m.id
         where m.project_id = any(%s::uuid[])
         group by m.id, p.name
         order by m.due_on nulls last, m.title
        """,
        (project_ids,),
    )
    if not rows:
        return None, NO_MILESTONES
    every = len(rows)
    if period is not None:
        rows = [r for r in rows if r["due_on"] and period.start <= r["due_on"] <= period.end]
        if not rows:
            return None, (
                f"{period.label} 사이에 기한이 있는 마일스톤이 없습니다. "
                f"이 사업의 마일스톤은 모두 {every}개입니다. 기간 없이 물으면 전체를 보여 드립니다."
            )
    many = len({r["project_name"] for r in rows}) > 1
    table_rows: list[WidgetRow] = []
    counts: dict[str, int] = {}
    for r in rows:
        state = _state(r, today)
        counts[state] = counts.get(state, 0) + 1
        values = {
            "title": r["title"],
            "due": r["due_on"].isoformat() if r["due_on"] else "-",
            "state": state,
            "issues": f"{r['done']}/{r['issues']}",
        }
        if many:
            values["project"] = r["project_name"]
        table_rows.append(WidgetRow(values=values))
    columns = [("title", "마일스톤"), ("due", "기한"), ("state", "상태"),
               ("issues", "이슈(닫힘/전체)")]
    if many:
        columns.insert(0, ("project", "사업"))
    data = intents._table(  # noqa: SLF001 — 표 모양은 일정 질문과 같다
        "entity_milestone", "마일스톤", None, columns, table_rows, project_ids
    )
    title = f"{period.label} 기한 마일스톤" if period else "마일스톤 현황"
    lines = [f"- 마일스톤 {len(rows)}개"] + [f"- {k} {n}개" for k, n in counts.items()]
    lines += [
        "- " + " · ".join(f"{label} {row.values[key]}" for key, label in columns)
        for row in table_rows
    ]
    note = (
        f"{today.isoformat()} 기준. 상태의 기한 안 닫힘·늦게 닫힘은 일정 준수율과 같은 판정이다"
        "(마지막으로 닫힌 날과 기한을 견줌). 기한 지남은 기한이 지났는데 열려 있는 것이다"
    )
    return (
        Block(slot=slot, template="DATA_TABLE", title=title, data=data, lines=lines, note=note),
        None,
    )
