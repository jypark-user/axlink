"""인포 템플릿 23종의 카탈로그 (ARC-012 · SWFR.WEB.001).

템플릿은 화면 조각이 아니라 **입력 계약**이다. 어떤 모양의 값이 들어오면 어떤 그림이
그려지는가를 한 곳에 적어 두고, 대시보드 위젯·AI 답변의 인포그래픽·관리자 화면이 모두
여기서 읽는다. 값은 시맨틱 레이어가 DB 에서 뽑고 모델은 이 중에서 고르기만 한다(절대 규칙 1·2).

프런트 types/api.ts 의 WidgetTemplate 과 widget.template CHECK(V18) 가 같은 목록이다.
렌더러(frontend/src/features/widgets/renderers.tsx)가 실제로 읽는 값과 어긋나면 안 된다.
"""

from dataclasses import dataclass

from app.common import korean

# 시간축 요구 수준
TIME_REQUIRED = "REQUIRED"  # 기간 차원이 없으면 뜻이 없다
TIME_OPTIONAL = "OPTIONAL"  # 있으면 추이, 없으면 범주
TIME_NONE = "NONE"  # 기간 차원을 쓰지 않는다

ANY = ("COUNT", "RATE_PCT", "DAYS", "PCT_POINT")


@dataclass(frozen=True)
class TemplateDef:
    key: str
    label: str  # 발주기관 어휘. 프런트 labels.ts 와 같다
    family: str  # 수치 | 추이 | 분포 | 구성 | 변화 | 점검
    purpose: str  # 무엇을 보여 주는 그림인가
    screen: str  # 화면에 무엇이 그려지는가 (제목·값·축·범례)
    when: str  # 언제 고르는가. 모델 프롬프트와 관리자 화면이 같은 문장을 쓴다
    measure_types: tuple[str, ...]  # 받는 지표 값 유형
    dims_min: int
    dims_max: int
    time_axis: str  # TIME_REQUIRED | TIME_OPTIONAL | TIME_NONE
    category_max: int | None  # 읽을 수 있는 범주 수 상한. 표 성격이면 None
    uses_total: bool  # 차원별 값 옆에 "전체" 값이 있어야 한다 (semantic.run 이 붙인다)
    uses_target: bool  # 지표의 목표값(target_value)을 긋는다
    uses_previous: bool  # 직전 구간 값과 비교한다
    options: tuple[str, ...]  # 렌더러가 읽는 spec.options 항목
    row_cap: int
    example_measure: str
    example_dimensions: tuple[str, ...]
    example_title: str
    chat: bool  # AI 답변의 인포그래픽으로 쓸 수 있는가
    note: str = ""  # 제약이나 아직 안 되는 것


_T = TemplateDef

CATALOG: tuple[TemplateDef, ...] = (
    # ---- 수치 · 지금 위치
    _T("STAT_CARD", "숫자 카드", "수치",
       "지표 하나의 현재 값",
       "제목, 큰 숫자와 단위, 직전 구간 대비 증감, 기간 축이 있으면 작은 추세선. "
       "임계값을 주면 색이 바뀐다",
       "숫자 하나를 묻는 질문. 차원 없이 전체 값, 또는 기간 축 하나로 추세선을 붙인다",
       ANY, 0, 1, TIME_OPTIONAL, None, True, False, True,
       ("unit", "threshold", "compareWithPrevious"), 100,
       "requirement_fulfillment_rate", ("period_month",), "요구사항 이행률", False),
    _T("BULLET_CHART", "불릿 차트", "수치",
       "값과 목표선의 거리",
       "범주마다 가로 막대 하나와 목표선. 목표는 지표의 목표값이고 threshold.warn 으로 "
       "덮어쓸 수 있다",
       "비율 지표를 목표와 견줄 때. 범주 8개 이하",
       ("RATE_PCT",), 0, 1, TIME_NONE, 8, True, True, False,
       ("unit", "threshold"), 100,
       "issue_resolution_rate", ("contractor_org",), "용역사별 일반 이슈 처리율 vs 목표", True),
    _T("SPARKLINE", "스파크라인", "수치",
       "계열별 잔추세",
       "계열마다 이름, 마지막 값, 작은 선. 축과 눈금은 없다",
       "여러 계열의 방향만 한눈에 볼 때. 기간 축 + 범주 축",
       ANY, 1, 2, TIME_REQUIRED, 8, False, False, False,
       ("unit",), 100,
       "issue_count", ("period_month", "issue_status"), "상태별 일반 이슈 잔추세", True),
    # ---- 추이 · 시간이 지나며
    _T("LINE_CHART", "추이 라인", "추이",
       "기간에 따른 값의 변화",
       "가로 기간 축, 세로 값 축, 선 하나 또는 범주별 여러 선과 범례",
       "추이를 물을 때 기본. 기간 구간 12개 이하",
       ANY, 1, 2, TIME_REQUIRED, 12, False, False, False,
       ("unit", "showLegend"), 100,
       "test_pass_rate", ("period_month",), "월별 시험 통과율", True),
    _T("AREA_CHART", "면적 추이", "추이",
       "기간에 따른 값의 변화, 선 아래를 채운다",
       "추이 라인과 같고 선 아래를 칠한다. 구간이 많아 선이 빽빽할 때 흐름이 더 잘 보인다",
       "기간 구간이 12개를 넘는 추이",
       ANY, 1, 2, TIME_REQUIRED, 36, False, False, False,
       ("unit", "showLegend"), 100,
       "progress_issue_pct", ("period_week",), "주별 일반 이슈 해결률 추이", True),
    _T("CUMULATIVE_FLOW", "누적 흐름", "추이",
       "등록이 쌓인 양과 지금 상태",
       "등록 시점 기간 축 위에 그때까지 쌓인 건수를 지금 상태별 띠로 나눠 쌓는다. 그 시점의 "
       "상태 이력이 아니다",
       "기간 축 + 상태 축 두 개일 때. 쌓인 것 중 지금 열린 것과 닫힌 것이 어떻게 갈리는지",
       ("COUNT",), 2, 2, TIME_REQUIRED, 8, False, False, False,
       ("unit", "showLegend"), 100,
       "issue_count", ("period_month", "issue_status"), "일반 이슈 누적 흐름(지금 상태 기준)", True,
       "상태는 지금 상태다. 과거 시점의 상태 분포는 상태 이력이 없어 그리지 못한다"),
    _T("CALENDAR_HEATMAP", "달력 히트맵", "추이",
       "일 단위 활동량",
       "달력 격자. 날짜 칸의 색 농도가 값이다",
       "일 축(period_day) 하나로 빈 날과 몰린 날을 볼 때",
       ("COUNT",), 1, 1, TIME_REQUIRED, 366, False, False, False,
       ("unit",), 100,
       "code_activity_count", ("period_day",), "일별 커밋·MR 활동", True),
    # ---- 분포 · 어디에 몰렸나
    _T("BAR_CHART", "막대 차트", "분포",
       "범주별 값 비교",
       "가로 범주 축, 세로 값 축, 막대. 두 번째 차원을 주면 범주 안에서 나란히 선다",
       "범주 비교의 기본. 범주 12개 이하",
       ANY, 1, 2, TIME_OPTIONAL, 12, False, False, False,
       ("unit", "sort", "stacked", "showLegend"), 100,
       "open_issue_count", ("issue_severity",), "심각도별 열린 일반 이슈", True),
    _T("HORIZONTAL_BAR_CHART", "가로 막대", "분포",
       "범주가 많을 때의 값 비교",
       "막대를 눕히고 범주 이름을 왼쪽에 둔다. 값 순으로 정렬해 낮은 것부터 눈에 들어온다",
       "범주가 12개를 넘거나 이름이 길 때. 담당자별, 산출물 22종",
       ANY, 1, 1, TIME_NONE, 40, False, False, False,
       ("unit", "sort"), 100,
       "work_product_approval_rate", ("work_product_type",), "산출물 22종 승인률", True),
    _T("STACKED_BAR_CHART", "누적 막대", "분포",
       "범주 안의 구성",
       "첫 차원이 막대, 둘째 차원이 막대 안의 조각과 범례",
       "차원 두 개이고 칸(범주 곱)이 40개 이하일 때",
       ("COUNT",), 2, 2, TIME_OPTIONAL, 40, False, False, False,
       ("unit", "showLegend"), 100,
       "issue_count", ("contractor_org", "issue_severity"), "용역사 × 심각도별 일반 이슈", True),
    _T("HEATMAP", "히트맵", "분포",
       "두 차원의 격자",
       "행이 첫 차원, 열이 둘째 차원, 칸의 색 농도가 값. 칸마다 숫자를 적는다",
       "차원 두 개이고 칸이 40개를 넘을 때. 활동 × 산출물 유형에서 구멍 찾기",
       ANY, 2, 2, TIME_OPTIONAL, None, False, False, False,
       ("unit",), 200,
       "work_product_missing_count", ("iso_activity", "work_product_type"),
       "활동 × 산출물 유형별 미제출", True),
    _T("PARETO", "파레토", "분포",
       "어디에 집중됐나",
       "값 내림차순 막대와 누적 비율 선. 상위 몇 개가 전체의 몇 %인지 보인다",
       "소수의 범주가 대부분을 차지하는지 볼 때. 담당자별 열린 이슈",
       ("COUNT",), 1, 1, TIME_NONE, 20, False, False, False,
       ("unit",), 100,
       "open_issue_count", ("assignee",), "담당자별 열린 일반 이슈 집중도", True),
    _T("TREEMAP", "트리맵", "분포",
       "범주별 크기 비교",
       "값에 비례한 사각형을 채운다. 큰 것이 먼저 보인다",
       "범주가 많고 크기 차이가 클 때",
       ("COUNT",), 1, 1, TIME_NONE, 30, False, False, False,
       ("unit",), 100,
       "work_product_missing_count", ("work_product_type",), "유형별 미제출 산출물 크기", True),
    # ---- 구성 · 무엇으로 이뤄졌나
    _T("PIE_CHART", "파이 차트", "구성",
       "전체 대비 비중",
       "원을 범주별로 나눈다. 범례에 비율을 적는다",
       "구성비. 범주 3개 이하",
       ("COUNT",), 1, 1, TIME_NONE, 3, False, False, False,
       ("showLegend",), 100,
       "open_risk_count", ("risk_status",), "상태별 열린 리스크", True),
    _T("DONUT_CHART", "도넛 차트", "구성",
       "전체 대비 비중과 합계",
       "가운데가 빈 원. 가운데에 합계를 쓴다",
       "구성비. 범주 4~6개. 건수 지표만 받는다(비율을 나눠 더하면 합계가 뜻이 없다)",
       ("COUNT",), 1, 1, TIME_NONE, 6, False, False, False,
       ("unit", "showLegend"), 100,
       "requirement_count", ("requirement_priority",), "우선순위별 요구사항 비중", True),
    _T("STATUS_FLOW", "상태 흐름", "구성",
       "단계별 분포",
       "한 줄 띠를 단계 순으로 나누고 아래에 단계별 값과 범례",
       "상태·단계 차원 하나로 흐름의 어디에 몰렸는지 볼 때. 건수 지표만 받는다",
       ("COUNT",), 1, 1, TIME_NONE, 8, False, False, False,
       ("unit",), 100,
       "requirement_count", ("requirement_status",), "요구사항 단계 분포", True),
    _T("RADAR_CHART", "방사형", "구성",
       "여러 축의 균형",
       "축이 방사형으로 뻗고 값을 이어 다각형을 그린다. 찌그러진 쪽이 처진 곳이다",
       "비율 지표를 범주 3~8개로 견줄 때",
       ("RATE_PCT",), 1, 1, TIME_NONE, 8, False, False, False,
       ("unit",), 100,
       "work_product_approval_rate", ("iso_activity",), "활동별 산출물 승인률 균형", True,
       "범주가 3개보다 적으면 다각형이 되지 않아 렌더러가 막대로 그린다"),
    # ---- 변화 · 순위와 기울기
    _T("SLOPE_CHART", "기울기 비교", "변화",
       "처음과 지금",
       "기간 축의 첫 구간과 마지막 구간만 두 기둥으로 세우고 범주마다 선으로 잇는다",
       "기간 축 + 범주 축에서 시작과 끝만 볼 때",
       ANY, 2, 2, TIME_REQUIRED, 10, False, False, False,
       ("unit",), 100,
       "issue_count", ("period_month", "contractor_org"), "용역사별 일반 이슈, 처음과 지금", True),
    _T("BUMP_CHART", "순위 변화", "변화",
       "기간별 순위",
       "기간마다 범주의 순위를 매기고 선으로 잇는다. 값이 아니라 등수다",
       "기간 축 + 범주 축에서 누가 앞서고 뒤졌는지 볼 때",
       ANY, 2, 2, TIME_REQUIRED, 10, False, False, False,
       ("showLegend",), 100,
       "issue_count", ("period_month", "issue_severity"), "심각도별 일반 이슈 순위 변화", True),
    # ---- 점검 · 하나씩 짚기
    _T("PROGRESS_LIST", "진행률 목록", "점검",
       "항목별 진행률",
       "항목마다 이름과 진행 막대, 값. 전체 값을 기준선으로 긋는다",
       "비율 지표를 항목별로 짚을 때. 항목이 많아도 된다",
       ("RATE_PCT",), 1, 1, TIME_NONE, None, True, False, False,
       ("unit", "sort"), 200,
       "requirement_fulfillment_rate", ("contractor_org",), "용역사별 요구사항 이행률", False),
    _T("CHECKLIST", "점검표", "점검",
       "항목별 되고 안 됨",
       "항목마다 이름과 체크 표시, 값. 열을 골라 보일 수 있다",
       "산출물 22종처럼 있고 없음을 하나씩 확인할 때",
       ANY, 1, 2, TIME_NONE, None, False, False, False,
       ("columns",), 200,
       "work_product_approval_rate", ("work_product_type",), "산출물 22종 승인 점검표", False),
    _T("DATA_TABLE", "표", "점검",
       "값을 그대로 읽는 표",
       "차원 열과 값 열. 열을 골라 보일 수 있고 정렬된다",
       "그림보다 숫자를 그대로 봐야 할 때. 차원 0~2개",
       ANY, 0, 2, TIME_OPTIONAL, None, False, False, False,
       ("columns", "sort", "unit"), 200,
       "issue_avg_resolution_days", ("assignee",), "담당자별 일반 이슈 평균 처리일", False),
    _T("GANTT_SUMMARY", "일정 요약", "점검",
       "항목별 계획 기간과 실적",
       "항목마다 기간 막대. 계획과 실적 열이 있어야 한다",
       "일정 화면 전용. 시맨틱 집계는 계획·실적 두 열을 만들지 못해 대시보드에서는 고르지 않는다",
       ANY, 1, 1, TIME_NONE, None, False, False, False,
       (), 200,
       "progress_wbs_pct", ("project",), "사업별 WBS 진척률",
       False, "시맨틱 집계로는 planned·actual 두 열이 안 나온다. 일정 화면(WBS)이 직접 그린다"),
)

BY_KEY: dict[str, TemplateDef] = {t.key: t for t in CATALOG}
TEMPLATES: tuple[str, ...] = tuple(t.key for t in CATALOG)

# 시간축이 있어야 뜻이 있는 그림. 차원을 안 주면 지표의 기본 차원 대신 기간 축을 붙인다.
TIME_TEMPLATES = frozenset(t.key for t in CATALOG if t.time_axis == TIME_REQUIRED)
# 항목을 하나씩 짚는 표 성격이라 행이 많아도 된다. 그래프는 이보다 많으면 못 읽는다.
CHAT_TEMPLATES = tuple(t.key for t in CATALOG if t.chat)

DEFAULT_LIMIT = 50


def is_template(value: str | None) -> bool:
    return value in BY_KEY


def row_cap(template: str) -> int:
    return BY_KEY[template].row_cap if template in BY_KEY else 100


def get(template: str) -> TemplateDef:
    return BY_KEY[template]


def fits(
    template: str,
    measure_type: str,
    dimensions: list[str],
    time_keys: set[str],
    *,
    strict: bool = True,
) -> str | None:
    """이 입력이 템플릿의 계약에 맞는가. 맞으면 None, 아니면 이유 한 줄.

    strict 는 모델이 고른 것을 바로잡을 때 쓴다. 지표 유형·차원 하한·기간축 유무까지 본다.
    validate(저장·미리보기)는 strict 를 끄고 굳은 제약(차원 초과·기간축 필수)만 막는다.
    차원이 모자란 그림은 그려지기는 하므로 사람이 고른 것을 거절하지 않는다. 범주 상한은
    값을 뽑아 봐야 알아서 막지 않고 행 상한으로 자른다.
    """
    t = BY_KEY.get(template)
    if t is None:
        return f"알 수 없는 위젯 템플릿: {template}"
    n = len(dimensions)
    has_time = any(d in time_keys for d in dimensions)
    if n > t.dims_max:
        return f"{korean.attach(t.label, '은')} 차원을 {t.dims_max}개까지 받습니다"
    if t.time_axis == TIME_REQUIRED and not has_time:
        return f"{korean.attach(t.label, '은')} 기간 차원이 있어야 합니다"
    if not strict:
        return None
    if measure_type not in t.measure_types:
        return f"{korean.attach(t.label, '은')} {'·'.join(t.measure_types)} 지표만 받습니다"
    if n < t.dims_min:
        return f"{korean.attach(t.label, '은')} 차원이 {t.dims_min}개 이상이어야 합니다"
    if t.time_axis == TIME_NONE and has_time:
        return f"{korean.attach(t.label, '은')} 기간 차원을 쓰지 않습니다"
    return None


_TIME_WORD = {
    TIME_REQUIRED: "기간 차원 필수",
    TIME_OPTIONAL: "기간 차원 선택",
    TIME_NONE: "기간 차원 없음",
}


def contract_summary(t: TemplateDef) -> str:
    """차원 수와 시간축을 한 토막으로. 모델이 값 모양과 맞춰 볼 수 있게."""
    dims = str(t.dims_min) if t.dims_min == t.dims_max else f"{t.dims_min}~{t.dims_max}"
    types = "모든 지표" if t.measure_types == ANY else "·".join(t.measure_types) + " 지표"
    return f"차원 {dims}개 · {_TIME_WORD[t.time_axis]} · {types}"


def prompt_guide(chat_only: bool = False) -> str:
    """모델 프롬프트에 넣는 템플릿 안내. 관리자 화면의 "언제 고르는가"와 같은 문장이다.

    템플릿 선택의 근거는 이 문장이다. 이름만 보고 고르지 말라고 첫 줄에 못 박는다.
    """
    rows = [t for t in CATALOG if (t.chat or not chat_only) and t.key != "GANTT_SUMMARY"]
    head = (
        "템플릿은 각 줄의 「언제 고르는가」를 근거로 고른다. 그림 이름의 인상으로 고르지 않는다. "
        "고른 차원 수·기간 차원 유무가 괄호 안 계약과 맞아야 한다."
    )
    lines = [
        f"- {t.key} ({t.label}, {contract_summary(t)}): 언제 고르는가 → {t.when}" for t in rows
    ]
    return head + "\n" + "\n".join(lines)


# 템플릿마다 "표시할 내용" 에 이렇게 적으면 된다는 문장. 위젯 추가 대화상자가 고른 템플릿
# 아래에 보여 주고, 누르면 그대로 채운다. 모델 프롬프트 안내(when)와 달리 사람이 읽고 따라 쓰는
# 문장이라 따로 둔다.
#
# 문장마다 그 문장이 가리키는 지표·차원을 같이 적는다. 시험이 그 조합이 카탈로그에 있고 템플릿
# 계약에 맞는지 본다(F-11: 요구사항 건수 지표 없이 「요구사항 구성비」 예문이 있었다).
# 추이는 스냅샷 지표로 적는다. 이행률·처리율 같은 비율을 기간 차원으로 나누면 추이가 아니라
# 「그 기간에 등록된 것의 비율」이 된다. 건수를 기간으로 나누면 등록 건수다.
Example = tuple[str, str, tuple[str, ...]]

PROMPT_EXAMPLES: dict[str, tuple[Example, ...]] = {
    "STAT_CARD": (
        ("요구사항 이행률 현재 값과 목표", "requirement_fulfillment_rate", ()),
        ("열린 이슈가 지금 몇 건인지", "open_issue_count", ()),
        ("이슈 하나를 닫는 데 평균 며칠 걸리는지", "issue_avg_resolution_days", ()),
    ),
    "BULLET_CHART": (
        ("용역사별 이슈 처리율을 목표선과 나란히", "issue_resolution_rate", ("contractor_org",)),
        ("요구사항 이행률이 목표 90% 에 얼마나 가까운지", "requirement_fulfillment_rate", ()),
        ("산출물 승인률 vs 목표", "deliverable_approval_rate", ()),
    ),
    "SPARKLINE": (
        ("월별 요구사항 이행률 잔추세", "snapshot_requirement_fulfillment_pct", ("period_month",)),
        ("주별로 등록된 이슈 건수 잔추세", "issue_count", ("period_week",)),
        ("등록 월별 이슈 건수를 지금 상태별 잔추세로", "issue_count",
         ("period_month", "issue_status")),
    ),
    "LINE_CHART": (
        ("월별 시험 통과율 추이", "test_pass_rate", ("period_month",)),
        ("주별 일반 이슈 해결률이 오르고 있는지", "progress_issue_pct", ("period_week",)),
        ("월별로 등록된 이슈 건수를 용역사별로", "issue_count", ("period_month", "contractor_org")),
    ),
    "AREA_CHART": (
        ("월별 요구사항 이행률이 어떻게 올라왔는지", "snapshot_requirement_fulfillment_pct",
         ("period_month",)),
        ("주별 일반 이슈 해결률 추이를 면적으로", "progress_issue_pct", ("period_week",)),
        ("월별 산출물 승인률 추이", "snapshot_work_product_approval_pct", ("period_month",)),
    ),
    "CUMULATIVE_FLOW": (
        ("월별로 등록된 이슈가 쌓인 양을 지금 상태로 나눠서", "issue_count",
         ("period_month", "issue_status")),
        ("주별 등록 이슈 누적을 지금 상태별로", "issue_count", ("period_week", "issue_status")),
        ("등록 월별 요구사항 누적을 지금 단계별로", "requirement_count",
         ("period_month", "requirement_status")),
    ),
    "CALENDAR_HEATMAP": (
        ("날짜별 커밋과 머지리퀘스트 활동량", "code_activity_count", ("period_day",)),
        ("일별 이슈 등록 건수를 달력으로", "issue_count", ("period_day",)),
        ("일별 코드 활동이 뜸한 날이 언제인지", "code_activity_count", ("period_day",)),
    ),
    "BAR_CHART": (
        ("열린 이슈가 심각도별로 몇 건인지", "open_issue_count", ("issue_severity",)),
        ("우선순위별 요구사항 이행률", "requirement_fulfillment_rate", ("requirement_priority",)),
        ("월별로 등록된 이슈 건수", "issue_count", ("period_month",)),
    ),
    "HORIZONTAL_BAR_CHART": (
        ("산출물 22종 각각의 승인률", "work_product_approval_rate", ("work_product_type",)),
        ("담당자별 열린 이슈 건수", "open_issue_count", ("assignee",)),
        ("용역사별 요구사항 이행률", "requirement_fulfillment_rate", ("contractor_org",)),
    ),
    "STACKED_BAR_CHART": (
        ("용역사별 열린 이슈를 심각도로 쌓아서", "open_issue_count",
         ("contractor_org", "issue_severity")),
        ("월별 등록 이슈 건수를 지금 상태로 쌓아서", "issue_count",
         ("period_month", "issue_status")),
        ("우선순위별 요구사항을 상태로 쌓아서", "requirement_count",
         ("requirement_priority", "requirement_status")),
    ),
    "HEATMAP": (
        ("29110 활동과 산출물 유형별로 미제출이 어디에 몰려 있는지", "work_product_missing_count",
         ("iso_activity", "work_product_type")),
        ("용역사와 심각도별 열린 이슈 밀도", "open_issue_count",
         ("contractor_org", "issue_severity")),
        ("담당자와 상태별 이슈 건수", "issue_count", ("assignee", "issue_status")),
    ),
    "PARETO": (
        ("열린 이슈가 어느 담당자에게 몰려 있는지", "open_issue_count", ("assignee",)),
        ("미제출 산출물이 어느 유형에 몰려 있는지", "work_product_missing_count",
         ("work_product_type",)),
        ("열린 리스크가 어느 상태에 몰려 있는지", "open_risk_count", ("risk_status",)),
    ),
    "TREEMAP": (
        ("미제출 산출물을 유형별 크기로", "work_product_missing_count", ("work_product_type",)),
        ("열린 이슈를 담당자별 크기로", "open_issue_count", ("assignee",)),
        ("요구사항을 우선순위별 크기로", "requirement_count", ("requirement_priority",)),
    ),
    "PIE_CHART": (
        ("열린 리스크가 상태별로 몇 건인지", "open_risk_count", ("risk_status",)),
        ("열린 리스크의 심각도 구성비", "open_risk_count", ("risk_severity",)),
        ("열린 이슈의 심각도 구성비", "open_issue_count", ("issue_severity",)),
    ),
    "DONUT_CHART": (
        ("우선순위별 요구사항 건수와 합계", "requirement_count", ("requirement_priority",)),
        ("심각도별 열린 리스크 비중", "open_risk_count", ("risk_severity",)),
        ("상태별 산출물 비중", "work_product_count", ("work_product_status",)),
    ),
    "STATUS_FLOW": (
        ("요구사항이 정의·구현·검증·인수 단계에 각각 몇 건 있는지", "requirement_count",
         ("requirement_status",)),
        ("산출물이 미제출·제출·승인 상태에 각각 몇 건 있는지", "work_product_count",
         ("work_product_status",)),
        ("이슈가 열림·진행·해결·종료 상태에 각각 몇 건 있는지", "issue_count",
         ("issue_status",)),
    ),
    "RADAR_CHART": (
        ("29110 활동별 산출물 승인률이 고른지", "work_product_approval_rate", ("iso_activity",)),
        ("용역사별 이슈 처리율이 고른지", "issue_resolution_rate", ("contractor_org",)),
        ("우선순위별 요구사항 이행률 균형", "requirement_fulfillment_rate",
         ("requirement_priority",)),
    ),
    "SLOPE_CHART": (
        ("용역사별 월 등록 이슈 건수, 첫 달과 마지막 달", "issue_count",
         ("period_month", "contractor_org")),
        ("심각도별 월 등록 이슈 건수, 첫 달과 마지막 달", "issue_count",
         ("period_month", "issue_severity")),
        ("등록 월 기준 상태별 요구사항 건수의 처음과 끝", "requirement_count",
         ("period_month", "requirement_status")),
    ),
    "BUMP_CHART": (
        ("월별로 심각도별 등록 이슈 건수 순위가 어떻게 바뀌는지", "issue_count",
         ("period_month", "issue_severity")),
        ("월별 등록 이슈 건수의 담당자 순위 변화", "issue_count", ("period_month", "assignee")),
        ("주별 용역사별 등록 이슈 건수 순위", "issue_count", ("period_week", "contractor_org")),
    ),
    "PROGRESS_LIST": (
        ("용역사별 요구사항 이행률을 진행 막대로", "requirement_fulfillment_rate",
         ("contractor_org",)),
        ("산출물 유형별 승인률 진행 막대", "work_product_approval_rate", ("work_product_type",)),
        ("우선순위별 요구사항 이행률 목록", "requirement_fulfillment_rate",
         ("requirement_priority",)),
    ),
    "CHECKLIST": (
        ("산출물 22종이 승인됐는지 하나씩 점검표로", "work_product_approval_rate",
         ("work_product_type",)),
        ("29110 활동별 산출물 승인 점검표", "work_product_approval_rate", ("iso_activity",)),
        ("요구사항 우선순위별 이행 점검표", "requirement_fulfillment_rate",
         ("requirement_priority",)),
    ),
    "DATA_TABLE": (
        ("담당자별 이슈 평균 처리일을 표로", "issue_avg_resolution_days", ("assignee",)),
        ("용역사와 심각도별 이슈 건수 표", "issue_count", ("contractor_org", "issue_severity")),
        ("산출물 유형별 미제출 건수 표", "work_product_missing_count", ("work_product_type",)),
    ),
    "GANTT_SUMMARY": (
        ("사업별 WBS 진척률", "progress_wbs_pct", ("project",)),
    ),
}


def prompt_examples(template: str) -> tuple[str, ...]:
    return tuple(text for text, _, _ in PROMPT_EXAMPLES.get(template, ()))
