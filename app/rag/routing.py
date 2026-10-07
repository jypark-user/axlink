"""질문 라우팅. 집계 질문인지 문서 질문인지 LLM 이 판단하고, 집계면 카탈로그에서 고른다.

위젯 생성(app/dashboard/generation.py)과 같은 원칙이다. 모델은 지표·차원·템플릿의
키를 고를 뿐이고 값은 시맨틱 레이어가 SQL 로 뽑는다(절대 규칙 1·2). 고른 키가
카탈로그에 없으면 집계 경로를 포기하고 문서 경로로 내려간다. 억지로 맞추지 않는다.
"""

from dataclasses import dataclass, field
from typing import Any

from app.ai.port import LlmPort
from app.dashboard import generation
from app.dashboard.widget_template import prompt_guide
from app.rag import entity_table, intents
from app.semantic.catalog import Catalog, MeasureDef

DOCUMENT = "DOCUMENT"
AGGREGATE = "AGGREGATE"
MIXED = "MIXED"
OVERVIEW = "OVERVIEW"  # 사업 현황 요약. 문서를 가리키지 않는 일반 질문 (ARC-015)
OFF_TOPIC = "OFF_TOPIC"  # 사업과 무관한 질문. 현황으로도 내려가지 않고 그렇다고 답한다
INTENT = "INTENT"  # 일정 질문 묶음(intents). 지표 하나로 답이 안 서는 비교·목록
CLARIFY = "CLARIFY"  # 두 뜻으로 읽히는 질문. 선택지를 내고 되묻는다

# 목록으로 물을 수 있는 색인 종류. 모델이 이 밖의 값을 주면 보통 문서 검색으로 간다.
LISTABLE: dict[str, str] = {
    "ISSUE": "일반 이슈",
    "REQUIREMENT": "요구사항",
    "RISK": "리스크",
    "DOCUMENT_UPLOAD": "산출물",
}

# 모델 출력을 JSON 객체 하나로 묶는다. 키 목록은 프롬프트가 말하고, 값의 검증(키가
# 카탈로그에 있는지)은 from_choice 가 한다. 속성을 일일이 적은 스키마는 쓰지 않는다.
# 09.14 실측에서 route·query 만 필수로 둔 스키마를 주자 qwen3:4b 가 선택 속성을 통째로
# 건너뛰어 "AGGREGATE 인데 measure 없음" 이 됐고, 객체라고만 묶으면 여섯 키를 다 채웠다.
CHOICE_SCHEMA: dict[str, Any] = {"type": "object"}

# 앞 대화를 프롬프트에 넣을 때의 한도. 최근 몇 턴을 보이고 답은 앞부분만 자른다. 요점은
# 앞에 있고, "둘이 왜 달라?" 처럼 두 턴을 가리키는 질문은 한 턴만으로는 못 푼다
PREVIOUS_TURNS = 3
PREVIOUS_ANSWER_CHARS = 500


@dataclass
class PreviousTurn:
    """앞선 질문·답 한 쌍. 후속 질문("그 방법의 흐름을 보여줘")이 무엇을 가리키는지 알려 준다."""

    question: str
    answer: str
    measure_key: str | None = None
    route_type: str | None = None
    topic: str | None = None  # 그때 판정이 뽑은 검색 핵심어. 지표가 없는 목록·현황 답의 주제

    def excerpt(self) -> str:
        text = " ".join(self.answer.split())
        if len(text) > PREVIOUS_ANSWER_CHARS:
            text = text[:PREVIOUS_ANSWER_CHARS] + "…"
        return text

    def render(self) -> str:
        tags = []
        if self.measure_key:
            tags.append(f"지표 {self.measure_key}")
        if self.topic:
            tags.append(f"주제어 {self.topic}")
        tail = f" ({', '.join(tags)})" if tags else ""
        return f"질문: {self.question}\n답{tail}: {self.excerpt()}"


def render_previous(turns: list[PreviousTurn]) -> str:
    """오래된 것부터, 마지막이 직전 턴이다."""
    return "\n\n".join(t.render() for t in turns)


@dataclass
class RouteDecision:
    type: str  # DOCUMENT | AGGREGATE
    rewritten: str | None = None  # 검색용으로 다듬은 질문. 모델이 안 주면 원문을 쓴다
    measure: MeasureDef | None = None
    dimensions: list[str] = field(default_factory=list)
    template: str | None = None
    title: str = ""
    listing: str | None = None  # 종류 전체를 나열하는 질문이면 그 source_type
    # 목록의 상태 조건. OPEN(처리 중) | CLOSED(완료) | ALL. 표를 만들 때 SQL 이 이걸로 거른다
    listing_status: str = entity_table.ALL
    # 앞 대화에 기대는 후속 질문인가. 그러면 판정을 캐시하지 않는다. 같은 문장이 다른 대화에서
    # 다른 뜻이기 때문이다
    follow_up: bool = False
    intent: str | None = None  # INTENT 일 때 intents 의 키
    period: str | None = None  # 기간 변화의 비교 단위 WEEK | MONTH
    options: list[str] = field(default_factory=list)  # CLARIFY 의 선택지 키
    related: list[str] = field(default_factory=list)  # 이어서 볼 만한 질문 키. 권장 질문 재료


# 권장 질문·선택지·누른 질문의 키. 모델이 고르고 서버가 다시 검증한다. 문장은 서버가 만든다.
#   intent:<묶음>[:WEEK|MONTH]  measure:<지표>  overview  list:<종류>:<상태>
OVERVIEW_KEY = "overview"
LIST = "LIST"
MAX_KEYS = 3


@dataclass(frozen=True)
class Target:
    kind: str  # INTENT | AGGREGATE | OVERVIEW | LIST
    key: str  # 정규화한 키
    intent: str | None = None
    period: str | None = None
    measure: MeasureDef | None = None
    listing: str | None = None
    listing_status: str = entity_table.ALL


def parse_key(catalog: Catalog, raw: object) -> Target | None:
    """키 하나를 검증한다. 모르는 묶음·폐기된 지표·없는 종류면 None 이다."""
    if not isinstance(raw, str):
        return None
    parts = [x.strip() for x in raw.strip().split(":")]
    head = parts[0].lower()
    if head == OVERVIEW_KEY and len(parts) == 1:
        return Target(kind=OVERVIEW, key=OVERVIEW_KEY)
    if head == "intent" and len(parts) in (2, 3):
        intent = parts[1].upper()
        if intent not in intents.INTENTS:
            return None
        period = None
        if intent == intents.PROGRESS_CHANGE:
            period = parts[2].upper() if len(parts) == 3 else intents.WEEK
            if period not in intents.PERIODS:
                return None
        elif len(parts) == 3:
            return None
        key = f"intent:{intent}" + (f":{period}" if period else "")
        return Target(kind=INTENT, key=key, intent=intent, period=period)
    if head == "measure" and len(parts) == 2:
        measure = catalog.measure(parts[1])
        if measure is None:
            return None
        return Target(kind=AGGREGATE, key=f"measure:{measure.key}", measure=measure)
    if head == "list" and len(parts) in (2, 3):
        listing = parts[1].upper()
        status = parts[2].upper() if len(parts) == 3 else entity_table.ALL
        if listing not in LISTABLE or status not in entity_table.STATUSES:
            return None
        return Target(
            kind=LIST, key=f"list:{listing}:{status}", listing=listing, listing_status=status
        )
    return None


def _keys(catalog: Catalog, raw: object) -> list[str]:
    """모델이 준 키 목록에서 검증을 통과한 것만, 순서를 지켜 겹침 없이."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        target = parse_key(catalog, item)
        if target is not None and target.key not in out:
            out.append(target.key)
    return out


def current_key(decision: "RouteDecision") -> str | None:
    """이번 판정이 답하는 키. 권장 질문에서 같은 것을 다시 내지 않으려고 쓴다."""
    if decision.type == INTENT and decision.intent:
        return f"intent:{decision.intent}" + (f":{decision.period}" if decision.period else "")
    if decision.type == AGGREGATE and decision.measure is not None:
        return f"measure:{decision.measure.key}"
    if decision.type == OVERVIEW:
        return OVERVIEW_KEY
    if decision.listing:
        return f"list:{decision.listing}:{decision.listing_status}"
    return None


def from_target(target: Target, question: str | None = None) -> "RouteDecision":
    """권장 질문을 눌렀을 때. 다시 분류하지 않는다. 재분류가 빗나가 같은 안내가 반복되지 않게."""
    if target.kind == INTENT:
        return RouteDecision(type=INTENT, intent=target.intent, period=target.period)
    if target.kind == OVERVIEW:
        return RouteDecision(type=OVERVIEW, rewritten=question)
    if target.kind == LIST:
        return RouteDecision(
            type=DOCUMENT,
            rewritten=question,
            listing=target.listing,
            listing_status=target.listing_status,
        )
    measure = target.measure
    assert measure is not None
    return RouteDecision(
        type=AGGREGATE,
        rewritten=question,
        measure=measure,
        dimensions=[],
        template="STAT_CARD",
        title=measure.label,
    )


def decide(
    catalog: Catalog, llm: LlmPort, question: str, previous: list[PreviousTurn] | None = None
) -> RouteDecision:
    result = llm.complete(
        system_prompt(catalog), user_content(question, previous), json_schema=CHOICE_SCHEMA
    )
    choice = generation.parse_choice(result.text)
    return from_choice(catalog, choice)


def user_content(question: str, previous: list[PreviousTurn] | None) -> str:
    """모델에 주는 질문. 앞 대화가 있으면 같이 준다. 이번 질문이 무엇을 가리키는지는 모델이
    앞 질문을 봐야 안다. 앞 대화가 없으면 질문 문장 그대로다(캐시 키와 같은 문자열)."""
    if not previous:
        return question
    return f"## 앞 대화 (마지막이 직전)\n{render_previous(previous)}\n\n## 이번 질문\n{question}"


def from_choice(catalog: Catalog, choice: dict[str, Any] | None) -> RouteDecision:
    """모델의 JSON 을 결정으로 바꾼다. 읽을 수 없거나 키가 틀리면 문서 경로다."""
    if not choice:
        return RouteDecision(type=DOCUMENT)
    rewritten = choice.get("query")
    rewritten = rewritten.strip() if isinstance(rewritten, str) and rewritten.strip() else None

    listing = str(choice.get("list") or "").strip().upper() or None
    if listing not in LISTABLE:
        listing = None
    listing_status = str(choice.get("listFilter") or "").strip().upper()
    if listing_status not in entity_table.STATUSES:
        listing_status = entity_table.ALL
    follow_up = choice.get("followUp") is True

    related = _keys(catalog, choice.get("related"))[:MAX_KEYS]

    route = str(choice.get("route") or "").strip().upper()
    measure_key = choice.get("measure")
    measure = catalog.measure(str(measure_key)) if measure_key else None
    if route == INTENT:
        intent = str(choice.get("intent") or "").strip().upper()
        period = str(choice.get("period") or "").strip().upper()
        target = parse_key(catalog, f"intent:{intent}:{period}" if period else f"intent:{intent}")
        target = target or parse_key(catalog, f"intent:{intent}")
        if target is not None:
            return RouteDecision(
                type=INTENT,
                rewritten=rewritten,
                intent=target.intent,
                period=target.period,
                follow_up=follow_up,
                related=[k for k in related if k != target.key],
            )
    if route == CLARIFY:
        options = _keys(catalog, choice.get("options"))[:MAX_KEYS]
        if len(options) >= 2:
            return RouteDecision(
                type=CLARIFY, rewritten=rewritten, options=options, follow_up=follow_up
            )
    if route == OFF_TOPIC and measure is None and listing is None:
        return RouteDecision(type=OFF_TOPIC, rewritten=rewritten, follow_up=follow_up)
    if route == OVERVIEW and measure is None:
        return RouteDecision(
            type=OVERVIEW,
            rewritten=rewritten,
            listing=listing,
            listing_status=listing_status,
            follow_up=follow_up,
            related=[k for k in related if k != OVERVIEW_KEY],
        )
    if route not in (AGGREGATE, OVERVIEW) or measure is None:
        # 집계로 못 셀 질문이어도 목록은 낼 수 있다. 둘은 따로 판정한다.
        return RouteDecision(
            type=DOCUMENT,
            rewritten=rewritten,
            listing=listing,
            listing_status=listing_status,
            follow_up=follow_up,
            related=related,
        )

    template = generation._template_of(choice)
    dimensions = generation._dimensions_of(choice, measure, catalog, template)
    if template is None or not generation._fits(template, measure, dimensions, catalog):
        template = generation._default_template(dimensions, catalog)
    title = choice.get("title")
    return RouteDecision(
        type=AGGREGATE,
        rewritten=rewritten,
        measure=measure,
        dimensions=dimensions,
        template=template,
        title=str(title).strip() if isinstance(title, str) and title.strip() else measure.label,
        listing=listing,
        listing_status=listing_status,
        follow_up=follow_up,
        related=[k for k in related if k != f"measure:{measure.key}"],
    )


def system_prompt(catalog: Catalog) -> str:
    measures = "\n".join(
        f"- {m.key}: {m.label}. {m.description} (허용 차원: {', '.join(m.allowed_dimensions)})"
        for m in catalog.active_measures()
    )
    dimensions = "\n".join(
        f"- {d.key}: {d.label}. {d.description}" for d in catalog.active_dimensions()
    )
    intent_keys = ", ".join(intents.INTENTS)
    return (
        "당신은 사업 관리 질의를 분류하는 도우미다. 수치를 만들지 않고 답도 쓰지 않는다. "
        "일정·계획 대비 진척을 묻는 질문은 INTENT 로 분류한다(아래 일정 질문 절). "
        "질문이 아래 카탈로그의 지표로 셀 수 있는 것(진척률·건수·비율·추이)이면 AGGREGATE, "
        "문서·이슈·회의록의 내용을 묻는 것이면 DOCUMENT, 사업 전체 현황을 통틀어 요약해 "
        '달라는 것("전체 현황 알려줘", "요약해 줘", "사업 잘 되고 있어?", "문제 있어?", '
        '"뭐가 걱정이야?", "전체적으로 괜찮은 거야?", "오늘 확인해야 할 거 있어?")이면 OVERVIEW '
        "로 분류한다. 일정·진척 하나만 묻는 질문은 OVERVIEW 가 아니다. "
        '"이슈가 몇 건이야?", "결함이 얼마나 나왔어?" 처럼 건수를 묻는 것은 AGGREGATE 다. '
        "지표는 질문의 대상(이슈·요구사항·리스크·산출물·진척)과 같은 대상의 것만 고른다. "
        '"요구사항이 몇 개야?" 처럼 그 대상의 건수 지표가 없으면 다른 대상의 지표를 쓰지 않고 '
        "그 종류의 목록(list, listFilter ALL)으로 낸다. 목록 표가 총 건수를 말한다. "
        "사업과 명백히 무관한 것(날씨, 일반 상식, 프로그래밍 문법, "
        "잡담)만 OFF_TOPIC 이다. 사업의 목적·범위·인수 조건·연동 방식·이번 달 목표처럼 "
        "사업에 대해 묻는 것은 무관이 아니라 DOCUMENT 다. 헷갈리면 DOCUMENT 로 둔다.\n"
        "## 일정 질문\n"
        "- PLAN_VS_ACTUAL: 계획(예정) 대비 실제 진척. \"계획보다 늦고 있어?\", \"일정대로 "
        "가고 있어?\", \"일정 지연되고 있나?\", \"예정보다 앞서 있어?\", \"계획 대비 몇 퍼센트 "
        "차이야?\", \"예상 일정 대비 진척률 어때?\"\n"
        "- BEHIND_TASKS: 계획보다 늦은 작업이 무엇인지·있는지. \"늦은 작업 뭐야?\", "
        "\"지연된 작업 있어?\", \"지연된 작업 "
        "목록\"\n"
        "- PROGRESS_CHANGE: 지난주·지난달보다 얼마나 진행됐는지. period 는 WEEK 또는 MONTH. "
        "\"지난주보다 얼마나 진행됐어?\"\n"
        "- DELAY_CAUSE: 왜 늦어졌는지, 지연 사유·원인\n"
        "진척률 값 하나나 추이 그림을 묻는 것(\"진척률 몇 퍼센트야?\", \"이번 달 진척 추세\")은 "
        "AGGREGATE 다.\n"
        "산출물 지표는 셋이 다르다. 파일이 올라왔는가는 제출률(progress_work_product_pct, "
        "wbs_deliverable_submitted_rate), 발주기관이 작업 완료를 확인·인정했는가는 완료 확인율"
        "(wbs_completion_rate)이다. \"산출물까지 확인된 진척\", \"완료가 확인된 작업\" 은 완료 "
        "확인율이다.\n"
        "## 되묻기\n"
        "질문이 두 가지 이상으로 읽히고 앞 대화로도 정할 수 없을 때만 CLARIFY 로 하고 options 에 "
        "후보 키 2~3개를 적는다(\"진도 괜찮아?\" 는 계획 대비 진척인지 전체 현황인지 갈린다). "
        "한쪽이 분명하면 되묻지 않는다. 사업 전체가 괜찮은지·무엇을 볼지 묻는 질문은 되묻지 않고 "
        "OVERVIEW 다. 분야를 말했으면(\"이슈 처리는 잘 되고 있어?\", \"품질은 어때?\") 그 분야 "
        "지표(AGGREGATE)나 OVERVIEW 로 답하고 되묻지 않는다.\n"
        "## 이어 볼 질문\n"
        "어느 경로든 related 에 이 질문 다음에 볼 만한 키를 0~3개 적는다. 질문과 관련 있는 "
        "것만 적고 억지로 채우지 않는다.\n"
        f"키 형식: intent:<{intent_keys} 중 하나>, intent:PROGRESS_CHANGE:WEEK, "
        "intent:PROGRESS_CHANGE:MONTH, measure:<지표 key>, overview, list:<종류>:<상태>\n"
        "출력은 JSON 객체 하나뿐이다. 설명을 붙이지 않는다.\n"
        '일정: {"route": "INTENT", "intent": "<묶음>", "period": "<WEEK|MONTH>", '
        '"query": "<검색용 핵심어>", "related": ["<키>"]}\n'
        '집계: {"route": "AGGREGATE", "measure": "<지표 key>", "dimensions": ["<차원 key>"], '
        '"template": "<템플릿>", "title": "<한국어 제목>", "query": "<검색용 핵심어>", '
        '"related": ["<키>"]}\n'
        '문서: {"route": "DOCUMENT", "query": "<검색용 핵심어>", "related": ["<키>"]}\n'
        '현황: {"route": "OVERVIEW", "query": "<검색용 핵심어>"}\n'
        '되묻기: {"route": "CLARIFY", "options": ["<키>", "<키>"]}\n'
        '무관: {"route": "OFF_TOPIC"}\n'
        '목록: {"route": "DOCUMENT", "list": "<종류>", "listFilter": "<상태>", '
        '"query": "<검색용 핵심어>"}\n'
        "목록은 이슈·요구사항·리스크·산출물 같은 종류를 나열하거나 현황을 묻는 질문에 쓴다"
        '("이슈 목록", "요구사항 뭐가 있어", "등록된 리스크", "완료된 이슈는 뭐가 있어", '
        '"아직 작업이 안 된 이슈", "미제출 산출물 목록"). '
        "상태 조건이 붙어도 나열을 묻는 것이면 목록이다. "
        '"심각한 이슈 있어?", "리스크 있어?", "가장 심각한 문제는 뭐야?" 처럼 그런 항목이 있는지 '
        "묻는 것도 목록이다(열린 이슈·열린 리스크). 일정 질문이 아니다. "
        '"가장 급한 작업", "먼저 처리할 것", "우선순위가 높은 이슈" 처럼 무엇부터 할지 묻는 '
        "질문도 목록이다. 열린 이슈(list ISSUE, listFilter OPEN)를 심각도 순으로 받아 답한다. "
        "종류는 "
        + ", ".join(f"{k}({v})" for k, v in LISTABLE.items())
        + " 중 하나다. 특정 항목의 내용을 묻는 질문에는 list 를 붙이지 않는다.\n"
        "listFilter 는 OPEN(아직 안 끝난 것), CLOSED(끝난 것), ALL(전부) 중 하나다. "
        '"아직 작업이 안 된", "처리 중인", "남은", "미해결" 은 OPEN 이고 '
        '"완료된", "닫힌", "처리된" 은 CLOSED 다. 조건이 없으면 ALL 이다.\n'
        "질문이 카탈로그 지표의 이름을 부르면(\"이행률\", \"처리율\", \"진척률\" 등) 값을 묻든, "
        "왜 그런지 묻든, 어떻게 올리는지 묻든 그 지표를 measure 로 고른다. 지표의 뜻과 움직이는 "
        "조건이 집계 값 절에 함께 오기 때문이다. 단 계획·예정·일정과 견주는 질문은 지표 "
        "이름이 있어도 일정 질문(INTENT)이 먼저다. "
        "지표 key 는 카탈로그에 있는 것만 쓴다. 맞는 지표가 없으면 DOCUMENT 다. "
        "차원은 0~2개이고 지표의 허용 차원에서만 고른다. 추이를 물으면 period_ 차원을 쓴다.\n"
        "입력에 '앞 대화' 절이 있으면 이번 질문이 그것을 가리키는지 본다. \"그 방법의 흐름을 "
        "보여줘\", \"왜 그래?\", \"더 자세히\", \"그림으로\", \"그건 어떻게 해결해?\", \"그 중에 "
        "지연된 건?\" 처럼 혼자서는 주제가 없는 질문은 후속 질문이다. 후속 질문은 앞 대화와 같은 "
        "주제로 분류하고 \"followUp\": true 를 붙인다. 주제는 이렇게 잇는다. 앞 답에 지표가 있으면 "
        "그 지표를 measure 로 쓴다. 앞 답이 목록·현황이었으면 이번 질문이 가리키는 항목(\"미제출 "
        "산출물\", \"지연 작업\", \"열린 이슈\" 등)에 맞는 카탈로그 지표를 measure 로 고른다. "
        "\"왜\", \"어떻게 해결\", \"줄이려면\", \"올리려면\" 은 그 지표의 산출 근거가 답하므로 "
        "AGGREGATE 다. 앞 답의 목록에 조건을 더하는 질문(\"그 중에 지연된 건\")은 같은 종류의 "
        "목록에 조건을 바꿔 다시 list 로 낸다. 앞 답에서 말한 방법·절차를 흐름·단계·그림으로 보여 "
        "달라는 것은 사업 현황(OVERVIEW)이 아니다. 앞 대화가 있어도 이번 질문만으로 주제가 서면 "
        "followUp 은 false 다.\n\n"
        f"## 지표\n{measures}\n\n## 차원\n{dimensions}\n\n"
        f"## 템플릿 (언제 고르는가)\n{prompt_guide(chat_only=True)}\n"
    )
