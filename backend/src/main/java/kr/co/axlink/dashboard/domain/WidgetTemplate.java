package kr.co.axlink.dashboard.domain;

public enum WidgetTemplate {
  STAT_CARD,
  BAR_CHART,
  LINE_CHART,
  PIE_CHART,
  PROGRESS_LIST,
  DATA_TABLE,
  CHECKLIST,
  GANTT_SUMMARY,
  /** 한 줄 100% 누적 띠 — 상태 단계별로 몇 건이 걸려 있는지 본다. */
  STATUS_FLOW,
  /** 두 차원 격자 — 어느 활동에서 막혀 있는지 농도로 본다. */
  HEATMAP,
  /** 면적 추이 — 구간이 길어 선이 빽빽할 때 흐름을 본다. */
  AREA_CHART,
  /** 누적 막대 — 범주 안에서 무엇이 얼마씩 차지하는지 본다. */
  STACKED_BAR_CHART,
  /** 가로 막대 — 항목이 많거나 이름이 길 때 순위를 본다. */
  HORIZONTAL_BAR_CHART,
  /** 도넛 — 구성비를 보되 가운데에 총계를 둔다. */
  DONUT_CHART,
  /** 방사형 — 항목별 이행률이 고른지 한눈에 본다. */
  RADAR_CHART,
  /** 누적 흐름 — 쌓이는 속도와 닫히는 속도를 겹쳐 본다. 벌어지면 적체다. */
  CUMULATIVE_FLOW,
  /** 파레토 — 막대 옆에 누적 비율선을 둬 어디에 몰렸는지 본다. */
  PARETO,
  /** 트리맵 — 칸이 많아 막대로는 안 보이는 구성비를 넓이로 본다. */
  TREEMAP,
  /** 기울기 — 두 시점 사이에 항목별로 얼마나 오르내렸는지 본다. */
  SLOPE_CHART,
  /** 순위 변화 — 기간마다 항목 순위가 어떻게 뒤바뀌는지 본다. */
  BUMP_CHART,
  /** 잔 추세 — 항목마다 한 줄짜리 추세선과 마지막 값을 나란히 본다. */
  SPARKLINE,
  /** 불릿 — 목표 대비 지금 어디까지 왔는지 본다. */
  BULLET_CHART,
  /** 달력 — 날짜별 활동의 공백 구간을 본다. */
  CALENDAR_HEATMAP;

  public static WidgetTemplate parse(String value) {
    if (value == null) {
      return null;
    }
    return WidgetTemplate.valueOf(value.toUpperCase(java.util.Locale.ROOT));
  }
}
