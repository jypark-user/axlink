"""일정 질문 묶음 (SWFR.RAG.005). 계획 대비 진척·늦은 작업·기간 변화·지연 사유.

지표 하나로는 기준일·계획값·보고값·산식이 한 번에 나오지 않는다. 같은 사업·같은 기준일의
값을 함께 뽑아 줄로 펴고, 모델은 그 줄만으로 문장을 쓴다(절대 규칙 1). 값은 진척 카드와 같은
dashboard.compute 와 일별 스냅샷에서 온다. 메뉴와 답의 수치가 어긋나면 버그다.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.common import clock, korean
from app.dashboard import service as progress_service
from app.db import fetch_all, fetch_one
from app.rag import blocks
from app.semantic.models import WidgetColumn, WidgetDataResponse, WidgetRow

PLAN_VS_ACTUAL = "PLAN_VS_ACTUAL"
BEHIND_TASKS = "BEHIND_TASKS"
PROGRESS_CHANGE = "PROGRESS_CHANGE"
DELAY_CAUSE = "DELAY_CAUSE"

INTENTS: dict[str, str] = {
    PLAN_VS_ACTUAL: "계획 대비 진척",
    BEHIND_TASKS: "계획보다 늦은 작업",
    PROGRESS_CHANGE: "기간별 진척 변화",
    DELAY_CAUSE: "지연 사유",
}
WEEK = "WEEK"
MONTH = "MONTH"
PERIODS = {WEEK: "지난주", MONTH: "지난달"}

# 결과 종류. NO_DATA 면 모델을 부르지 않고 notice 만 내보낸다
ANSWER = "ANSWER"
PARTIAL = "PARTIAL"
NO_DATA = "NO_DATA"

MAX_PROJECTS = 5
TABLE_ROWS = 20
PROMPT_ROWS = 10


# 계획선은 실제 계획값이 아니다. 답에 늘 함께 보인다. 숫자를 넣지 않는다(검문 근거가 흐려진다)
PLAN_FORMULA = (
    "계획 진척률은 추정값이다. WBS 말단 작업마다 계획 시작일부터 종료일까지 중 기준일까지 "
    "지난 날의 비율을 구하고(시작 전은 없음, 종료 뒤는 전부) 가중치로 평균했다. "
    "보고 진척률은 용역사가 WBS 실적 열에 적은 값의 가중 평균이다. 차이는 두 백분율의 "
    "차(%p)다."
)
# 답 끝에 서버가 붙이는 한 줄. 모델이 빠뜨려도 추정임은 늘 보인다
PLAN_FOOTNOTE = "계획 진척률은 실제 계획값이 아니라 WBS 작업 기간을 날짜로 안분한 추정값입니다."
# 모델에게 주는 지시. 표로 미루지 말고 핵심 숫자를 본문이 말하게 한다(숫자를 넣지 않는다)
_SAY_NUMBERS = (
    "- 답의 첫 문장에 기준일, 계획 진척률(추정), 보고 진척률, 차이(%p)를 위 숫자 그대로 쓴다"
)
_NO_PLAN = (
    "WBS 계획 기간과 보고 진척률이 아직 없어 계획 대비 진척을 계산할 수 없습니다. "
    "용역사가 시작일·종료일·가중치·실적 열이 있는 WBS 파일을 저장소에 커밋하면 답할 수 있습니다."
)


@dataclass
class IntentResult:
    intent: str
    status: str  # ANSWER | PARTIAL | NO_DATA
    title: str
    lines: list[str] = field(default_factory=list)  # 프롬프트와 수치 검문의 재료
    dates: list[date] = field(default_factory=list)  # 값의 기준일. 검문이 시점을 맞춘다
    table: WidgetDataResponse | None = None
    note: str | None = None  # 표 아래 설명. 산식·범위
    notice: str | None = None  # 서버 문안. 부분 답에서 못 한 것, 값이 없는 이유
    # 모델이 쓸 것이 없으면 서버가 쓴 답 전체. 숫자는 DB 값 그대로다
    server_text: str | None = None
    footnote: str | None = None  # 모델 답 끝에 서버가 붙이는 설명

    def block(self, slot: int) -> blocks.Block | None:
        if self.table is None:
            return None
        return blocks.Block(
            slot=slot,
            template="DATA_TABLE",
            title=self.title,
            data=self.table,
            lines=self.lines,
            note=self.note,
        )


def today() -> date:
    return clock.today()


def run(
    cur: Any, intent: str, period: str | None, project_ids: list[str], at: date | None = None
) -> IntentResult:
    at = at or today()
    projects = _projects(cur, project_ids)
    if intent == PLAN_VS_ACTUAL:
        return plan_vs_actual(cur, projects, at)
    if intent == BEHIND_TASKS:
        return behind_tasks(cur, projects, at)
    if intent == DELAY_CAUSE:
        return delayed_tasks(cur, projects, at)
    if intent == PROGRESS_CHANGE:
        return progress_change(cur, projects, period if period in PERIODS else WEEK)
    raise ValueError(f"모르는 질문 묶음: {intent}")


# ---------------------------------------------------------------- 계획 대비


def plan_vs_actual(cur: Any, projects: list[dict[str, Any]], at: date) -> IntentResult:
    """같은 사업·같은 기준일의 계획(추정)·보고·차이·늦은 작업 수."""
    result = IntentResult(PLAN_VS_ACTUAL, ANSWER, "계획 대비 진척")
    rows: list[WidgetRow] = []
    fallbacks: list[tuple[str, str, date]] = []  # (사업, 서버 문장, 기준일)
    for project in projects[:MAX_PROJECTS]:
        name = project["name"]
        progress = progress_service.compute(cur, project["id"], at)
        if progress.wbsPlanned is not None and progress.wbs.value is not None:
            planned = _pct(progress.wbsPlanned)
            actual = _pct(progress.wbs.value)
            diff = round(actual - planned, 2)
            behind = len(progress.behind)
            leaves = progress.wbs.denominator or 0
            # 가중치 없는 WBS(L2)는 기간 비례 가중치로 낸 추정이다(DEC-19)
            kind = "WBS 실적"
            if progress.estimated:
                kind = "WBS 실적, 가중치 미지정이라 계획 기간 비례 추정"
            result.lines.append(
                f"- {name} (기준일 {at.isoformat()}): 계획 진척률(추정) {format_value(planned)}%, "
                f"보고 진척률({kind}) {format_value(actual)}%, 차이 {_signed(diff)}%p "
                f"({_direction(diff)}), 말단 작업 {leaves}건 중 {behind}건이 계획선보다 늦음"
            )
            rows.append(
                WidgetRow(
                    values={
                        "project": name,
                        "base_date": at.isoformat(),
                        "planned": f"{format_value(planned)}%",
                        "actual": f"{format_value(actual)}%",
                        "diff": f"{_signed(diff)}%p",
                        "behind": f"{leaves}건 중 {behind}건",
                    }
                )
            )
            result.dates.append(at)
            continue
        found = _without_plan(cur, project, progress)
        if found is not None:
            fallbacks.append((name, found[0], found[1]))

    if not rows:
        # 비교한 사업이 없다. 허용된 보고값이 있으면 서버가 그 값과 날짜만 말한다(부분 답)
        if fallbacks:
            result.status = PARTIAL
            result.server_text = " ".join(text for _, text, _ in fallbacks)
        else:
            result.status = NO_DATA
            result.notice = _NO_PLAN
        return result

    for _, text, when in fallbacks:
        result.lines.append(f"- {text}")
        result.dates.append(when)
    if len(projects) > MAX_PROJECTS:
        result.lines.append(f"- 사업 {len(projects)}개 중 앞 {MAX_PROJECTS}개만 보였다")
    result.lines.append(_SAY_NUMBERS)
    result.footnote = PLAN_FOOTNOTE
    # 사업 하나면 표가 문장을 되풀이할 뿐이다. 여럿일 때만 표로 견준다
    if len(rows) > 1:
        result.table = _table(
            "progress_plan_vs_actual",
            "계획 대비 진척",
            "%",
            [
                ("project", "사업"),
                ("base_date", "기준일"),
                ("planned", "계획 진척률(추정)"),
                ("actual", "보고 진척률"),
                ("diff", "차이"),
                ("behind", "늦은 작업"),
            ],
            rows,
            [p["id"] for p in projects],
        )
        result.note = PLAN_FORMULA
    missing = [name for name, _, _ in fallbacks]
    if missing:
        result.status = PARTIAL
        result.notice = (
            f"{', '.join(missing)}은(는) WBS 계획 기간이 없어 계획과 비교하지 못했습니다."
        )
    return result


def _without_plan(
    cur: Any, project: dict[str, Any], progress: Any
) -> tuple[str, date] | None:
    """WBS 를 지금 못 읽는 사업. 허용된 보고값이 있을 때만 그 값과 날짜를 밝히는 문장."""
    name = project["name"]
    snap = fetch_one(
        cur,
        """
        select snapshot_date, wbs_actual_pct from progress_snapshot
         where project_id = %s and wbs_actual_pct is not null
         order by snapshot_date desc limit 1
        """,
        (project["id"],),
    )
    if snap is not None:
        value = float(snap["wbs_actual_pct"])
        when = snap["snapshot_date"]
        return (
            f"{korean.attach(name, '은')} 지금 WBS 계획 기간을 읽을 수 없어 계획과 비교할 수 "
            f"없습니다. 마지막으로 확인된 보고 진척률(WBS 실적)은 {when.isoformat()} 스냅샷의 "
            f"{format_value(value)}%입니다.",
            when,
        )
    if progress.representative is not None and progress.basis in _BASIS_LABEL:
        value = _pct(progress.representative)
        return (
            f"{korean.attach(name, '은')} WBS 계획 기간이 없어 계획과 비교할 수 없습니다. "
            f"대표 진척률은 {_BASIS_LABEL[progress.basis]} 기준 {format_value(value)}%입니다"
            f"(기준일 {progress.baseDate}).",
            date.fromisoformat(progress.baseDate),
        )
    return None


_BASIS_LABEL = {"ISSUE": "일반 이슈 해결률", "WORK_PRODUCT": "산출물 제출률"}


# ---------------------------------------------------------------- 늦은 작업


def behind_tasks(cur: Any, projects: list[dict[str, Any]], at: date) -> IntentResult:
    """계획선보다 늦은 말단 작업. 진척 카드의 지연 작업과 같은 기준(1%p 여유)이다."""
    result = IntentResult(BEHIND_TASKS, ANSWER, "계획보다 늦은 작업")
    items: list[tuple[float, dict[str, str]]] = []
    with_plan = 0
    leaves = 0
    for project in projects[:MAX_PROJECTS]:
        plan_rows = progress_service.current_wbs_rows(cur, project["id"])
        if not plan_rows:
            continue
        with_plan += 1
        leaves += len(plan_rows)
        for r in plan_rows:
            planned_ratio = r.planned_at(at)
            if r.actual is None or r.actual + 0.01 >= planned_ratio:
                continue
            planned, actual = _pct(planned_ratio), _pct(r.actual)
            diff = round(actual - planned, 2)
            items.append(
                (
                    diff,
                    {
                        "project": project["name"],
                        "task": f"{r.wbs_id} {r.name}".strip(),
                        "end": r.end.isoformat() if r.end else "-",
                        "planned": f"{format_value(planned)}%",
                        "actual": f"{format_value(actual)}%",
                        "diff": f"{_signed(diff)}%p",
                    },
                )
            )
    if not with_plan:
        result.status = NO_DATA
        result.notice = (
            "WBS 파일이 없어 어떤 작업이 계획보다 늦었는지 알 수 없습니다. 용역사가 작업별 "
            "시작일·종료일·실적이 있는 WBS 파일을 저장소에 커밋하면 답할 수 있습니다."
        )
        return result

    items.sort(key=lambda t: t[0])
    result.dates.append(at)
    total = len(items)
    if total == 0:
        result.lines.append(
            f"- 기준일 {at.isoformat()}: 계획선보다 늦은 말단 작업 없음 (말단 작업 {leaves}건 중)"
        )
        return result
    shown = items[:PROMPT_ROWS]
    head = f"- 기준일 {at.isoformat()}: 말단 작업 {leaves}건 중 {total}건이 계획선보다 늦음"
    if total > len(shown):
        head += f". 아래는 차이가 큰 앞 {len(shown)}건"
    result.lines.append(head)
    for _, v in shown:
        result.lines.append(
            f"- {v['task']} ({v['project']}, 종료 예정 {v['end']}): 계획 {v['planned']}, "
            f"실적 {v['actual']}, 차이 {v['diff']}"
        )
    result.table = _table(
        "progress_behind_tasks",
        "계획보다 늦은 작업",
        None,
        [
            ("task", "작업"),
            ("project", "사업"),
            ("end", "종료 예정"),
            ("planned", "계획(추정)"),
            ("actual", "실적"),
            ("diff", "차이"),
        ],
        [WidgetRow(values=v) for _, v in items[:TABLE_ROWS]],
        [p["id"] for p in projects],
        truncated=total > TABLE_ROWS,
    )
    shown_rows = min(total, TABLE_ROWS)
    scope = f"총 {total}건" if shown_rows >= total else f"총 {total}건 중 앞 {shown_rows}건"
    result.note = f"기준일 {at.isoformat()} {scope}. 계획선은 추정이다. {PLAN_FORMULA}"
    return result


# ---------------------------------------------------------------- 지연 작업


def delayed_tasks(cur: Any, projects: list[dict[str, Any]], at: date) -> IntentResult:
    """지연 작업과 그 사유를 묻는 질문의 재료. 지연은 종료일이 기준일 전에 지났는데 실적이
    100% 가 아닌 말단 작업이다(IM-009 5.1). 계획선보다 뒤처졌을 뿐 종료일이 남은 작업(계획
    뒤짐)은 지연이 아니다. 계획 뒤짐 목록은 behind_tasks 가 따로 낸다."""
    result = IntentResult(DELAY_CAUSE, ANSWER, "지연 작업")
    items: list[tuple[date, dict[str, str]]] = []
    with_plan = 0
    leaves = 0
    for project in projects[:MAX_PROJECTS]:
        plan_rows = progress_service.current_wbs_rows(cur, project["id"])
        if not plan_rows:
            continue
        with_plan += 1
        leaves += len(plan_rows)
        for r in plan_rows:
            if r.end is None or r.end >= at or r.actual is None or r.actual + 0.0001 >= 1.0:
                continue
            items.append(
                (
                    r.end,
                    {
                        "project": project["name"],
                        "task": f"{r.wbs_id} {r.name}".strip(),
                        "end": r.end.isoformat(),
                        "actual": f"{format_value(_pct(r.actual))}%",
                    },
                )
            )
    if not with_plan:
        result.status = NO_DATA
        result.notice = (
            "WBS 파일이 없어 어떤 작업이 지연됐는지 알 수 없습니다. 용역사가 작업별 "
            "시작일·종료일·실적이 있는 WBS 파일을 저장소에 커밋하면 답할 수 있습니다."
        )
        return result

    items.sort(key=lambda t: t[0])
    result.dates.append(at)
    total = len(items)
    if total == 0:
        result.lines.append(
            f"- 기준일 {at.isoformat()}: 종료일이 지났는데 끝나지 않은 지연 작업 없음 "
            f"(말단 작업 {leaves}건 중)"
        )
        return result
    shown = items[:PROMPT_ROWS]
    head = (
        f"- 기준일 {at.isoformat()}: 말단 작업 {leaves}건 중 지연 작업 {total}건"
        " (종료일이 지났는데 실적이 100%가 아님)"
    )
    if total > len(shown):
        head += f". 아래는 종료일이 이른 앞 {len(shown)}건"
    result.lines.append(head)
    for _, v in shown:
        result.lines.append(
            f"- 지연 작업 {v['task']} ({v['project']}): 종료 예정 {v['end']}, 실적 {v['actual']}"
        )
    result.table = _table(
        "progress_delayed_tasks",
        "지연 작업",
        None,
        [("task", "작업"), ("project", "사업"), ("end", "종료 예정"), ("actual", "실적")],
        [WidgetRow(values=v) for _, v in items[:TABLE_ROWS]],
        [p["id"] for p in projects],
        truncated=total > TABLE_ROWS,
    )
    shown_rows = min(total, TABLE_ROWS)
    scope = f"총 {total}건" if shown_rows >= total else f"총 {total}건 중 앞 {shown_rows}건"
    result.note = (
        f"기준일 {at.isoformat()} {scope}. 지연은 종료일이 기준일 전에 지났는데 실적이 100%가 "
        "아닌 작업이다. 계획선보다 뒤처졌지만 종료일이 남은 작업은 들지 않는다."
    )
    return result


# ---------------------------------------------------------------- 기간 변화


def progress_change(cur: Any, projects: list[dict[str, Any]], period: str) -> IntentResult:
    """가장 최근 스냅샷과 지난주(지난달) 같은 날의 스냅샷. 그날이 없으면 가장 가까운 앞
    날짜를 쓰고 그 날짜를 밝힌다. 앞 스냅샷이 아예 없으면 비교할 수 없다고 한다."""
    word = PERIODS[period]
    result = IntentResult(PROGRESS_CHANGE, ANSWER, f"{word} 대비 진척 변화")
    failed: list[str] = []  # 비교하지 못한 사업
    plain: list[str] = []  # 비교하지 못한 사업마다 서버가 쓰는 문장
    for project in projects[:MAX_PROJECTS]:
        name = project["name"]
        span = fetch_one(
            cur,
            """
            select min(snapshot_date) as oldest, max(snapshot_date) as latest from progress_snapshot
             where project_id = %s and representative_pct is not null
            """,
            (project["id"],),
        )
        if span is None or span["latest"] is None:
            failed.append(name)
            plain.append(f"{korean.attach(name, '은')} 진척 스냅샷이 아직 없습니다.")
            continue
        end = span["latest"]
        latest = _snapshot_on(cur, project["id"], end)
        target = _back(end, period)
        base = _snapshot_on(cur, project["id"], target)
        now_value = float(latest["representative_pct"])
        if base is None:
            failed.append(name)
            plain.append(
                f"{korean.attach(name, '은')} {target.isoformat()} 이전 스냅샷이 없어 "
                f"{korean.attach(word, '과')} 비교할 수 없습니다. 가장 오래된 스냅샷은 "
                f"{span['oldest'].isoformat()}이고, 가장 최근 스냅샷({end.isoformat()})의 "
                f"진척률은 {format_value(now_value)}%입니다."
            )
            continue
        then = base["snapshot_date"]
        then_value = float(base["representative_pct"])
        diff = round(now_value - then_value, 2)
        line = (
            f"- {name}: {then.isoformat()} 진척률 {format_value(then_value)}% → "
            f"{end.isoformat()} 진척률 {format_value(now_value)}%, 변화 {_signed(diff)}%p"
        )
        if then != target:
            line += f" ({target.isoformat()} 스냅샷이 없어 가장 가까운 앞 날짜 값을 씀)"
        if latest["level"] != base["level"]:
            line += (
                f". 두 날의 진척 산정 수준이 다르다({base['level']} → {latest['level']}). "
                "그대로 견주면 안 된다"
            )
        result.lines.append(line)
        result.dates += [then, end]
    if not result.lines:
        # 비교한 사업이 없다. 무엇이 없는지와 있는 값을 서버가 그대로 말한다
        result.status = NO_DATA
        result.server_text = " ".join(plain) if plain else None
        result.notice = (
            "진척 스냅샷이 아직 없어 기간 변화를 계산할 수 없습니다. 일별 스냅샷이 쌓이면 "
            "답할 수 있습니다."
        )
    elif failed:
        result.status = PARTIAL
        result.notice = " ".join(plain)
    return result


def _snapshot_on(cur: Any, project_id: str, day: date) -> dict[str, Any] | None:
    """그날 또는 그 앞의 가장 가까운 스냅샷."""
    return fetch_one(
        cur,
        """
        select snapshot_date, level, representative_pct from progress_snapshot
         where project_id = %s and representative_pct is not null and snapshot_date <= %s
         order by snapshot_date desc limit 1
        """,
        (project_id, day),
    )


def _back(end: date, period: str) -> date:
    if period == WEEK:
        return end - timedelta(days=7)
    # 지난달 같은 날. 그달에 그날이 없으면 그달 말일
    year, month = (end.year, end.month - 1) if end.month > 1 else (end.year - 1, 12)
    day = end.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


# ---------------------------------------------------------------- 공통


def available(cur: Any, intent: str, project_ids: list[str]) -> bool:
    """권장 질문으로 내도 되는가. 눌렀을 때 같은 '없음' 안내로 끝날 것은 내지 않는다."""
    if not project_ids:
        return False
    if intent == PROGRESS_CHANGE:
        row = fetch_one(
            cur,
            """
            select 1 from progress_snapshot
             where project_id = any(%s::uuid[]) and representative_pct is not null
             group by project_id having count(*) >= 2 limit 1
            """,
            (project_ids,),
        )
        return row is not None
    return any(progress_service.current_wbs_rows(cur, pid) for pid in project_ids[:MAX_PROJECTS])


def _projects(cur: Any, project_ids: list[str]) -> list[dict[str, Any]]:
    if not project_ids:
        return []
    return fetch_all(
        cur,
        "select id::text as id, name from project where id = any(%s::uuid[]) order by name",
        (project_ids,),
    )


def _table(
    measure: str,
    label: str,
    unit: str | None,
    columns: list[tuple[str, str]],
    rows: list[WidgetRow],
    project_ids: list[str],
    truncated: bool = False,
) -> WidgetDataResponse:
    return WidgetDataResponse(
        measure=measure,
        measureLabel=label,
        unit=unit,
        dimensions=[],
        columns=[WidgetColumn(key=k, label=v, type="string") for k, v in columns],
        rows=rows,
        total=None,
        previousTotal=None,
        target=None,
        appliedProjectIds=list(project_ids),
        truncated=truncated,
        generatedAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def format_value(value: float) -> str:
    """answer.format_value 와 같은 표기. 집계 줄과 같은 꼴이라야 검문이 같은 값으로 본다.
    answer 가 routing 을 거쳐 이 모듈을 부르므로 가져오지 않고 둔다."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _pct(ratio: float) -> float:
    """진척 서비스는 0~1 비율이다. 스냅샷·카탈로그와 같은 소수 둘째 자리 백분율로."""
    return round(ratio * 100, 2)


def _signed(value: float) -> str:
    if value > 0:
        return f"+{format_value(value)}"
    if value < 0:
        return f"-{format_value(-value)}"
    return "0"


def _direction(diff: float) -> str:
    if diff < 0:
        return "계획보다 늦음"
    if diff > 0:
        return "계획보다 앞섬"
    return "계획과 같음"
