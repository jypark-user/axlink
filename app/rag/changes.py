"""「지난 보고 이후 변경된 사항을 요약해줘」 (착수보고 대표 질의 변경·증분).

모델은 이 질문을 현황 요약으로 읽어 지금 값(진척률·미제출 산출물)만 늘어놓았다. 무엇이
바뀌었는지는 말하지 못했다(11-23 실측). 변경은 기간 안에 생긴 일을 센 것이라 표준 모델에서
바로 센다. 수치는 전부 SQL 이 낸다(절대 규칙 1).

「지난 보고」의 날짜는 시스템이 모른다. 보고 일정을 수집하지 않기 때문이다. 질문에 기간
(최근 N일, 이번 달 등)이 없으면 7일 전부터 오늘까지로 보고, 그렇게 봤다고 표 설명에 적는다.
"""

import re
from datetime import date, timedelta
from typing import Any

from app.db import fetch_one
from app.rag import entity_table, intents
from app.rag.blocks import Block
from app.rag.question_period import ActivityRange, activity_range
from app.semantic.models import WidgetRow

_ASKS = re.compile(
    r"변경\s*(?:된|사항|내용|점|분)|바뀐|바뀌었|달라진|달라졌|변동\s*사항|새로\s*생긴"
)
# 특정 지표의 변화는 그 경로가 답한다. 「변경 요청서」는 산출물 이름이다
_NOT = re.compile(r"진척률|진척도|준수율|이행률|변경\s*요청")
DEFAULT_DAYS = 7

# 사업 시간대 날짜로 기간 안인지
_IN = "(({col}) at time zone 'Asia/Seoul')::date between %(start)s and %(end)s"


def asks(question: str) -> bool:
    return bool(_ASKS.search(question)) and not _NOT.search(question)


def window(question: str, today: date) -> tuple[ActivityRange, bool]:
    """(기간, 기본값을 썼는가)."""
    period = activity_range(question, today)
    if period is not None:
        return period, False
    return ActivityRange(today - timedelta(days=DEFAULT_DAYS), today), True


_COUNTS = (
    # (키, 구분, SQL). 각 SQL 은 %(projects)s·%(start)s·%(end)s 를 받는다
    ("issues_new", "새로 등록된 이슈",
     "select count(*) as n from issue where project_id = any(%(projects)s::uuid[]) and "
     + _IN.format(col="source_created_at")),
    ("issues_done", "해결·종료된 이슈",
     "select count(*) as n from issue where project_id = any(%(projects)s::uuid[]) and "
     + _IN.format(col="resolved_at")),
    ("commits", "커밋",
     "select count(*) as n from code_change where project_id = any(%(projects)s::uuid[]) "
     "and kind = 'COMMIT' and " + _IN.format(col="occurred_at")),
    ("prs", "PR",
     "select count(*) as n from code_change where project_id = any(%(projects)s::uuid[]) "
     "and kind <> 'COMMIT' and " + _IN.format(col="occurred_at")),
    ("documents", "새로 올라온 문서",
     "select count(*) as n from document_upload where project_id = any(%(projects)s::uuid[]) "
     "and " + _IN.format(col="created_at")),
    ("submitted", "제출된 산출물",
     "select count(*) as n from work_product where project_id = any(%(projects)s::uuid[]) "
     "and " + _IN.format(col="submitted_at")),
    ("approved", "승인된 산출물",
     "select count(*) as n from work_product where project_id = any(%(projects)s::uuid[]) "
     "and " + _IN.format(col="approved_at")),
    ("risks_new", "새로 식별된 리스크",
     # identified_at 은 날짜 열이다. 시간대를 씌우면 하루 앞으로 밀린다
     "select count(*) as n from risk where project_id = any(%(projects)s::uuid[]) and "
     "identified_at between %(start)s and %(end)s"),
    ("risks_closed", "종료된 리스크",
     "select count(*) as n from risk where project_id = any(%(projects)s::uuid[]) and "
     + _IN.format(col="closed_at")),
)


def build(
    cur: Any, question: str, project_ids: list[str], slot: int, today: date | None = None
) -> Block | None:
    if not project_ids:
        return None
    today = today or intents.today()
    period, defaulted = window(question, today)
    params = {"projects": project_ids, "start": period.start, "end": period.end}
    rows: list[WidgetRow] = []
    lines: list[str] = []
    for _key, label, sql in _COUNTS:
        got = fetch_one(cur, sql, params)
        n = int(got["n"]) if got else 0
        rows.append(WidgetRow(values={"item": label, "value": f"{n}건"}))
        lines.append(f"- {label} {n}건")

    active = entity_table.build(cur, "REQUIREMENT", entity_table.ALL, project_ids, 1, period)
    n_active = active.total if active is not None else 0
    rows.append(WidgetRow(values={"item": "활동이 있는 요구사항", "value": f"{n_active}건"}))
    lines.append(f"- 활동이 있는 요구사항 {n_active}건")

    if len(project_ids) == 1:
        progress = _progress(cur, project_ids[0], period)
        if progress is not None:
            value, line = progress
            rows.append(WidgetRow(values={"item": "진척률", "value": value}))
            lines.append(line)

    columns = [("item", "구분"), ("value", "기간 안")]
    data = intents._table(  # noqa: SLF001 — 표 모양은 일정 질문과 같다
        "entity_changes", "변경 사항", None, columns, rows, project_ids
    )
    note = f"{period.label} 사이에 생긴 일을 센 값이다"
    if defaulted:
        note += f". 지난 보고 날짜는 시스템에 없어 {DEFAULT_DAYS}일 전부터 셌다"
    # 11-23 실측에서 모델이 구분별 건수를 더해 「변경 n건」이라 했다가 수치 검문에 막혔다
    note += (
        ". 요구사항 활동은 기간 안에 연결된 이슈가 생겼거나 커밋·PR 이 붙은 것이다"
        ". 구분마다 세는 대상이 달라 건수를 서로 더하지 않는다"
        ". 생긴 일이 없는 구분은 묶어서 없었다고 말한다"
    )
    return Block(
        slot=slot,
        template="DATA_TABLE",
        title=f"{period.label} 변경 사항",
        data=data,
        lines=lines,
        note=note,
    )


def _progress(cur: Any, project_id: str, period: ActivityRange) -> tuple[str, str] | None:
    """기간 시작 무렵과 끝 무렵 스냅샷의 진척률. 둘 다 있어야 변화를 말한다."""
    sql = """
        select snapshot_date, representative_pct from progress_snapshot
         where project_id = %s and representative_pct is not null and snapshot_date <= %s
         order by snapshot_date desc limit 1
    """
    end = fetch_one(cur, sql, (project_id, period.end))
    start = fetch_one(cur, sql, (project_id, period.start))
    if end is None:
        return None
    now = float(end["representative_pct"])
    fmt = intents.format_value
    if start is None or start["snapshot_date"] == end["snapshot_date"]:
        day = end["snapshot_date"].isoformat()
        return (
            f"{fmt(now)}% ({day}, 비교할 앞 스냅샷 없음)",
            f"- 진척률 {day} {fmt(now)}%. 기간 시작 무렵 스냅샷이 없어 변화는 모른다",
        )
    then = float(start["representative_pct"])
    diff = round(now - then, 2)
    a, b = start["snapshot_date"].isoformat(), end["snapshot_date"].isoformat()
    sign = "+" if diff > 0 else ""
    return (
        f"{fmt(then)}% → {fmt(now)}% ({sign}{fmt(diff)}%p)",
        f"- 진척률 {a} {fmt(then)}% → {b} {fmt(now)}%, 변화 {sign}{fmt(diff)}%p",
    )
