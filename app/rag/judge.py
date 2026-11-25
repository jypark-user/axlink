"""AI 판단 답변 방식 (ARC-034).

지표 기반(기본)은 모델이 질문을 지표·문서·목록 중 하나로 판정하고, 서버가 그 하나만 집계해 넘긴다.
AI 판단은 판정 단계를 두지 않는다. 서버가 사업의 자원(핵심 지표, WBS 작업, 스냅샷 추이, 요구사항·
이슈·리스크·결함·산출물 목록)과 질문에 닿는 문서 조각을 한 번에 모아 넘기고, 모델이 그 안에서
무엇을 볼지 고르고 해석·원인 연결·우선순위·조치 제안까지 한다.

바뀌지 않는 것(절대 규칙). 자원의 값은 메뉴 화면과 같은 시맨틱 레이어·표준 모델에서 서버가 뽑는다.
모델은 그 값을 옮겨 쓸 뿐 계산하지 않고, 내보내는 문장은 같은 수치 검문(number_guard)을 지난다.
자원과 문서 밖의 사실은 말하지 않는다. 모델 호출은 질문당 한 번이다.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.auth.models import AuthPrincipal
from app.common import errors
from app.dashboard import service as progress_service
from app.db import fetch_all
from app.rag import answer, entity_table, number_guard
from app.rag.routing import PreviousTurn, render_previous
from app.rag.search import RetrievedChunk
from app.semantic import service as semantic
from app.semantic.models import WidgetOptions, WidgetQuery, WidgetSpec

STRUCTURED = "STRUCTURED"
AI_JUDGE = "AI_JUDGE"
MODES = (STRUCTURED, AI_JUDGE)
LABELS = {STRUCTURED: "지표 기반", AI_JUDGE: "AI 판단"}

# 자원으로 넣는 지표. 순서가 프롬프트 순서다. 카탈로그에 없거나 값이 없으면 건너뛴다
METRICS: tuple[str, ...] = (
    "progress_representative_pct",
    "progress_planned_pct",
    "progress_variance_pct",
    "progress_behind_task_count",
    "schedule_compliance_rate",
    "requirement_fulfillment_rate",
    "issue_count",
    "open_issue_count",
    "issue_resolution_rate",
    "defect_count",
    "open_defect_count",
    "defect_resolution_rate",
    "open_risk_count",
    "risk_resolution_rate",
    "deliverable_approval_rate",
    "work_product_missing_count",
    "code_activity_count",
)
# 나눠 센 지표. 모델이 목록 행을 세어 「심각도 높음 3건」을 만들지 않게 서버가 센다
BREAKDOWNS: tuple[tuple[str, str], ...] = (
    ("open_issue_count", "issue_severity"),
    ("open_risk_count", "risk_severity"),
    ("issue_count", "issue_status"),
)
# 목록 자원. (표준 모델 종류, 상태). 앞부분만 넣고 전체 건수는 범위 줄이 말한다
LISTS: tuple[tuple[str, str], ...] = (
    ("REQUIREMENT", entity_table.ALL),
    ("ISSUE", entity_table.OPEN),
    ("DEFECT", entity_table.ALL),
    ("RISK", entity_table.ALL),
    ("WORK_PRODUCT", entity_table.ALL),
)
LIST_LIMIT = 30
SNAPSHOT_DAYS = 14
MAX_PROJECTS = 3

SYSTEM_PROMPT = (
    "당신은 발주기관 담당자를 돕는 사업 관리 분석가다. 한국어로 답한다.\n"
    "아래 '사업 자원' 과 '근거 문서' 가 이 사업에 대해 아는 전부다. 그 안에서만 판단한다.\n"
    "규칙:\n"
    "1. 질문에 답하는 데 필요한 자원을 스스로 골라 쓴다. 여러 자원을 엮어 해석하고, 원인을 잇고, "
    "무엇이 더 급한지 판단하고, 확인하거나 조치할 일을 제안해도 된다. 판단과 제안은 그렇다고 "
    "밝히고, 그 판단의 근거가 된 자원을 함께 말한다.\n"
    "2. 수치는 자원과 문서에 적힌 값을 그대로만 쓴다. 더하거나 빼거나 나누어 새 수치를 만들지 "
    "않는다. 비율은 %, 백분율의 차이는 %p 로 쓰고, 값의 기준일이 있으면 함께 말한다.\n"
    "3. 자원과 문서로 답할 수 없으면 '지금 사업 자원에서는 확인할 수 없다' 고 말하고 지어내지 "
    "않는다. 사업과 무관한 질문에는 사업 관련 질문만 답한다고 말한다.\n"
    "4. 문서를 인용한 문장 끝에는 [1] 처럼 근거 문서 번호를, 사업 자원을 쓴 문장 끝에는 "
    "[자원: 절 이름] 을 붙인다.\n"
    "5. 항목의 지금 상태는 목록 자원의 상태를 따른다. 문서 속 계획·논의 문장을 지금 상태로 "
    "말하지 않는다.\n"
    "6. 결론을 먼저 한두 문장으로 말하고, 필요하면 근거와 판단을 짧은 문단이나 '- ' 목록으로 "
    "덧붙인다. 인사말과 사족은 넣지 않는다.\n"
    '7. 출력은 {"answer": "<답변>"} 꼴의 JSON 객체 하나다. 생각 과정은 쓰지 않는다.'
)


@dataclass
class Section:
    title: str
    lines: list[str]
    as_of: frozenset[number_guard.DateKey] = frozenset()


@dataclass
class Resources:
    sections: list[Section] = field(default_factory=list)

    def add(self, title: str, lines: list[str], as_of: frozenset = frozenset()) -> None:
        if lines:
            self.sections.append(Section(title, lines, as_of))

    def facts(self) -> list[number_guard.Fact]:
        out: list[number_guard.Fact] = []
        for s in self.sections:
            out += number_guard.facts_from_lines(s.lines, f"자원 {s.title}", s.title, s.as_of)
        return out

    def subjects(self) -> frozenset[str]:
        return number_guard.DOMAIN_TERMS | number_guard.keywords(
            " ".join(s.title for s in self.sections)
        )


def build(cur: Any, principal: AuthPrincipal, scope: list[str], at: date) -> Resources:
    """사업 자원을 모은다. 값은 전부 메뉴 화면과 같은 집계·표준 모델에서 온다."""
    res = Resources()
    projects = _projects(cur, scope[:MAX_PROJECTS])
    ids = [p["id"] for p in projects]
    if not ids:
        return res
    res.add("사업", [f"- {p['name']}" for p in projects])
    stamp = frozenset({(at.year, at.month, at.day)})
    metric_lines: list[str] = []
    for key in METRICS:
        lines = _metric(cur, principal, key, ids)
        metric_lines += lines
    res.add(f"핵심 지표 (기준 {at.isoformat()})", metric_lines, stamp)
    split_lines: list[str] = []
    for key, dim in BREAKDOWNS:
        split_lines += _metric(cur, principal, key, ids, (dim,))
    res.add("나눠 센 값", split_lines, stamp)
    for p in projects:
        res.add(f"WBS 작업 · {p['name']}", _wbs_lines(cur, p["id"], at), stamp)
        res.add(f"스냅샷 추이 · {p['name']}", _snapshot_lines(cur, p["id"]))
    for entity, status in LISTS:
        table = entity_table.build(cur, entity, status, ids, LIST_LIMIT)
        if table is not None:
            res.add(table.title, [f"- {table.scope_line}", *table.lines])
    return res


def user_prompt(
    question: str,
    resources: Resources,
    chunks: list[RetrievedChunk],
    previous: list[PreviousTurn] | None = None,
) -> str:
    parts = [f"## 질문\n{question}"]
    if previous:
        parts.append("## 앞 대화 (마지막이 직전)\n" + render_previous(previous))
    parts.append(
        "## 사업 자원\n"
        + "\n\n".join(f"### {s.title}\n" + "\n".join(s.lines) for s in resources.sections)
    )
    if chunks:
        parts.append(
            "## 근거 문서\n"
            + "\n\n".join(answer._evidence(i, c) for i, c in enumerate(chunks, 1))  # noqa: SLF001
        )
    else:
        parts.append("## 근거 문서\n(질문에 닿는 문서 조각 없음)")
    return "\n\n".join(parts)


def _projects(cur: Any, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    return fetch_all(
        cur,
        "select id::text as id, name from project where id = any(%s::uuid[]) order by name",
        (ids,),
    )


def _metric(
    cur: Any, principal: AuthPrincipal, key: str, ids: list[str], dims: tuple[str, ...] = ()
) -> list[str]:
    widget = WidgetSpec(
        template="BAR_CHART" if dims else "STAT_CARD",
        title=key,
        query=WidgetQuery(measure=key, dimensions=list(dims), filters=[], projectScope=list(ids)),
        options=WidgetOptions(),
    )
    try:
        data = semantic.run(cur, principal, widget)
    except errors.ApiError as exc:
        if exc.code in ("CATALOG_VALIDATION_FAILED", "VALIDATION_FAILED"):
            return []
        raise
    lines = [line for line in answer.aggregate_lines(data) if not line.startswith("- 산출 근거")]
    if not lines or all("값이 없음" in line or "값 없음" in line for line in lines):
        return []
    # 지표 이름이 줄 머리에 있어야 모델이 어느 값인지 안다. 범주 없는 집계는 이미 그렇다
    return lines


def _wbs_lines(cur: Any, project_id: str, at: date) -> list[str]:
    rows = progress_service.current_wbs_rows(cur, project_id)
    out: list[str] = []
    for r in rows:
        actual = "실적 모름" if r.actual is None else f"실적 {_pct(r.actual)}%"
        planned = f"계획선 {_pct(r.planned_at(at))}%"
        period = f"{r.start.isoformat() if r.start else '?'}~{r.end.isoformat() if r.end else '?'}"
        late = " · 종료일 지남, 미완료" if r.end and r.end < at and (r.actual or 0) < 1 else ""
        deliverable = f" · 산출물 {r.deliverable}" if r.deliverable else ""
        out.append(
            f"- {r.wbs_id} {r.name} · 기간 {period} · 가중치 {answer.format_value(r.weight)}"
            f" · {actual} · {planned}{deliverable}{late}"
        )
    return out


def _snapshot_lines(cur: Any, project_id: str) -> list[str]:
    rows = fetch_all(
        cur,
        """
        select snapshot_date, representative_pct, wbs_planned_pct, behind_task_count
          from progress_snapshot where project_id = %s::uuid
         order by snapshot_date desc limit %s
        """,
        (project_id, SNAPSHOT_DAYS),
    )
    out = []
    for r in reversed(rows):
        rep, plan = r["representative_pct"], r["wbs_planned_pct"]
        rep_text = "값 없음" if rep is None else f"{answer.format_value(float(rep))}%"
        plan_text = "" if plan is None else f", 계획선 {answer.format_value(float(plan))}%"
        out.append(
            f"- {r['snapshot_date'].isoformat()}: 진척률 {rep_text}{plan_text}, "
            f"지연 작업 {r['behind_task_count']}건"
        )
    return out


def _pct(ratio: float) -> str:
    return answer.format_value(round(ratio * 100, 1))
