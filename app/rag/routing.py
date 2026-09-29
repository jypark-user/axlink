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
from app.rag import entity_table
from app.semantic.catalog import Catalog, MeasureDef

DOCUMENT = "DOCUMENT"
AGGREGATE = "AGGREGATE"
MIXED = "MIXED"
OVERVIEW = "OVERVIEW"  # 사업 현황 요약. 문서를 가리키지 않는 일반 질문 (ARC-015)
OFF_TOPIC = "OFF_TOPIC"  # 사업과 무관한 질문. 현황으로도 내려가지 않고 그렇다고 답한다

# 목록으로 물을 수 있는 색인 종류. 모델이 이 밖의 값을 주면 보통 문서 검색으로 간다.
LISTABLE: dict[str, str] = {
    "ISSUE": "이슈",
    "REQUIREMENT": "요구사항",
    "RISK": "리스크",
    "DOCUMENT_UPLOAD": "산출물",
}

# 모델 출력을 JSON 객체 하나로 묶는다. 키 목록은 프롬프트가 말하고, 값의 검증(키가
# 카탈로그에 있는지)은 from_choice 가 한다. 속성을 일일이 적은 스키마는 쓰지 않는다.
# 09.14 실측에서 route·query 만 필수로 둔 스키마를 주자 qwen3:4b 가 선택 속성을 통째로
# 건너뛰어 "AGGREGATE 인데 measure 없음" 이 됐고, 객체라고만 묶으면 여섯 키를 다 채웠다.
CHOICE_SCHEMA: dict[str, Any] = {"type": "object"}

# 앞 대화 답을 프롬프트에 넣을 때 자르는 길이. 요점은 앞부분에 있다
PREVIOUS_ANSWER_CHARS = 700


@dataclass
class PreviousTurn:
    """직전 질문·답. 후속 질문("그 방법의 흐름을 보여줘")이 무엇을 가리키는지 알려 준다."""

    question: str
    answer: str
    measure_key: str | None = None
    route_type: str | None = None

    def excerpt(self) -> str:
        text = " ".join(self.answer.split())
        if len(text) > PREVIOUS_ANSWER_CHARS:
            text = text[:PREVIOUS_ANSWER_CHARS] + "…"
        return text


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


def decide(
    catalog: Catalog, llm: LlmPort, question: str, previous: PreviousTurn | None = None
) -> RouteDecision:
    result = llm.complete(
        system_prompt(catalog), user_content(question, previous), json_schema=CHOICE_SCHEMA
    )
    choice = generation.parse_choice(result.text)
    return from_choice(catalog, choice)


def user_content(question: str, previous: PreviousTurn | None) -> str:
    """모델에 주는 질문. 앞 대화가 있으면 같이 준다. 이번 질문이 무엇을 가리키는지는 모델이
    앞 질문을 봐야 안다. 앞 대화가 없으면 질문 문장 그대로다(캐시 키와 같은 문자열)."""
    if previous is None:
        return question
    subject = f"\n앞 답의 지표: {previous.measure_key}" if previous.measure_key else ""
    return (
        f"## 앞 대화\n질문: {previous.question}\n답: {previous.excerpt()}{subject}\n\n"
        f"## 이번 질문\n{question}"
    )


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

    route = str(choice.get("route") or "").strip().upper()
    measure_key = choice.get("measure")
    measure = catalog.measure(str(measure_key)) if measure_key else None
    if route == OFF_TOPIC and measure is None and listing is None:
        return RouteDecision(type=OFF_TOPIC, rewritten=rewritten, follow_up=follow_up)
    if route == OVERVIEW and measure is None:
        return RouteDecision(
            type=OVERVIEW,
            rewritten=rewritten,
            listing=listing,
            listing_status=listing_status,
            follow_up=follow_up,
        )
    if route not in (AGGREGATE, OVERVIEW) or measure is None:
        # 집계로 못 셀 질문이어도 목록은 낼 수 있다. 둘은 따로 판정한다.
        return RouteDecision(
            type=DOCUMENT,
            rewritten=rewritten,
            listing=listing,
            listing_status=listing_status,
            follow_up=follow_up,
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
    )


def system_prompt(catalog: Catalog) -> str:
    measures = "\n".join(
        f"- {m.key}: {m.label}. {m.description} (허용 차원: {', '.join(m.allowed_dimensions)})"
        for m in catalog.active_measures()
    )
    dimensions = "\n".join(
        f"- {d.key}: {d.label}. {d.description}" for d in catalog.active_dimensions()
    )
    return (
        "당신은 사업 관리 질의를 분류하는 도우미다. 수치를 만들지 않고 답도 쓰지 않는다. "
        "질문이 아래 카탈로그의 지표로 셀 수 있는 것(진척률·건수·비율·추이)이면 AGGREGATE, "
        "문서·이슈·회의록의 내용을 묻는 것이면 DOCUMENT, 사업이 전반적으로 어떤지를 묻는 "
        '것("잘 되고 있어?", "문제 있어?", "현황 알려줘", "요약해 줘", "뭐가 걱정이야?")이면 '
        "OVERVIEW 로 분류한다. 사업과 명백히 무관한 것(날씨, 일반 상식, 프로그래밍 문법, "
        "잡담)만 OFF_TOPIC 이다. 사업의 목적·범위·인수 조건·연동 방식·이번 달 목표처럼 "
        "사업에 대해 묻는 것은 무관이 아니라 DOCUMENT 다. 헷갈리면 DOCUMENT 로 둔다.\n"
        "출력은 JSON 객체 하나뿐이다. 설명을 붙이지 않는다.\n"
        '집계: {"route": "AGGREGATE", "measure": "<지표 key>", "dimensions": ["<차원 key>"], '
        '"template": "<템플릿>", "title": "<한국어 제목>", "query": "<검색용 핵심어>"}\n'
        '문서: {"route": "DOCUMENT", "query": "<검색용 핵심어>"}\n'
        '현황: {"route": "OVERVIEW", "query": "<검색용 핵심어>"}\n'
        '무관: {"route": "OFF_TOPIC"}\n'
        '목록: {"route": "DOCUMENT", "list": "<종류>", "listFilter": "<상태>", '
        '"query": "<검색용 핵심어>"}\n'
        "목록은 이슈·요구사항·리스크·산출물 같은 종류를 나열하거나 현황을 묻는 질문에 쓴다"
        '("이슈 목록", "요구사항 뭐가 있어", "등록된 리스크", "완료된 이슈는 뭐가 있어", '
        '"아직 작업이 안 된 이슈", "미제출 산출물 목록"). '
        "상태 조건이 붙어도 나열을 묻는 것이면 목록이다. "
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
        "조건이 집계 값 절에 함께 오기 때문이다. "
        "지표 key 는 카탈로그에 있는 것만 쓴다. 맞는 지표가 없으면 DOCUMENT 다. "
        "차원은 0~2개이고 지표의 허용 차원에서만 고른다. 추이를 물으면 period_ 차원을 쓴다.\n"
        "입력에 '앞 대화' 절이 있으면 이번 질문이 그것을 가리키는지 본다. \"그 방법의 흐름을 "
        "보여줘\", \"왜 그래?\", \"더 자세히\", \"그림으로\" 처럼 혼자서는 주제가 없는 질문은 "
        "후속 질문이다. 후속 질문은 앞 대화와 같은 주제로 분류하고(앞 답의 지표가 있으면 그 "
        "지표를 measure 로), \"followUp\": true 를 붙인다. 앞 답에서 말한 방법·절차를 흐름·단계·"
        "그림으로 보여 달라는 것은 사업 현황(OVERVIEW)이 아니다. 이번 질문만으로 주제가 서면 "
        "followUp 은 false 다.\n\n"
        f"## 지표\n{measures}\n\n## 차원\n{dimensions}\n\n"
        f"## 템플릿 (언제 고르는가)\n{prompt_guide(chat_only=True)}\n"
    )
