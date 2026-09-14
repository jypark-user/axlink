"""위젯 템플릿 23종. 프런트 types/api.ts 의 WidgetTemplate 과 widget.template CHECK(V18) 가
같은 목록이다. LLM 은 이 중에서 고르기만 한다(절대 규칙 2).
"""

TEMPLATES: tuple[str, ...] = (
    "STAT_CARD",
    "BAR_CHART",
    "LINE_CHART",
    "PIE_CHART",
    "PROGRESS_LIST",
    "DATA_TABLE",
    "CHECKLIST",
    "GANTT_SUMMARY",
    "STATUS_FLOW",
    "HEATMAP",
    "AREA_CHART",
    "STACKED_BAR_CHART",
    "HORIZONTAL_BAR_CHART",
    "DONUT_CHART",
    "RADAR_CHART",
    "CUMULATIVE_FLOW",
    "PARETO",
    "TREEMAP",
    "SLOPE_CHART",
    "BUMP_CHART",
    "SPARKLINE",
    "BULLET_CHART",
    "CALENDAR_HEATMAP",
)

# 항목을 하나씩 짚는 표 성격이라 행이 많아도 된다. 그래프는 이보다 많으면 못 읽는다.
_WIDE_TEMPLATES = frozenset({"DATA_TABLE", "PROGRESS_LIST", "CHECKLIST", "HEATMAP"})

# 시간축이 있어야 뜻이 있는 그림. 차원을 안 주면 지표의 기본 차원 대신 기간 축을 붙인다.
TIME_TEMPLATES = frozenset(
    {"LINE_CHART", "AREA_CHART", "CUMULATIVE_FLOW", "SPARKLINE", "CALENDAR_HEATMAP",
     "SLOPE_CHART", "BUMP_CHART"}
)

DEFAULT_LIMIT = 50


def is_template(value: str | None) -> bool:
    return value in TEMPLATES


def row_cap(template: str) -> int:
    return 200 if template in _WIDE_TEMPLATES else 100
