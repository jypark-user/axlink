package kr.co.axlink.rag.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetRow;
import kr.co.axlink.rag.dto.SseInfographicEvent;
import kr.co.axlink.semantic.domain.AggregateContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 모델이 고른 그림을 서버가 데이터 모양으로 걸러내는지 본다. */
class RagOrchestratorInfographicTest {

  private static WidgetDataResponse data(String unit, List<Number> values) {
    List<WidgetRow> rows = values.stream()
        .map(v -> new WidgetRow(Map.<String, Object>of("d0", "k" + v, "value", v)))
        .toList();
    return new WidgetDataResponse("m", "지표", unit, List.of("dim"), List.of(), rows,
        null, null, null, List.of(), false, Instant.EPOCH);
  }

  private static AggregateContext ctx(WidgetDataResponse d, boolean withDimension) {
    return new AggregateContext("m", withDimension ? List.of("dim") : List.of(),
        List.of(), Set.of(), d);
  }

  private static WidgetTemplate chosen(AggregateContext c, WidgetTemplate requested) {
    Optional<SseInfographicEvent> e = RagOrchestrator.infographic(c, requested);
    return e.map(SseInfographicEvent::template).orElse(null);
  }

  @Test
  @DisplayName("모델이 고른 형태가 데이터에 맞으면 그대로 쓴다")
  void honoursValidRequest() {
    AggregateContext c = ctx(data("건", List.of(1, 2, 3)), true);
    assertThat(chosen(c, WidgetTemplate.PIE_CHART)).isEqualTo(WidgetTemplate.PIE_CHART);
    assertThat(chosen(c, WidgetTemplate.BAR_CHART)).isEqualTo(WidgetTemplate.BAR_CHART);
    assertThat(chosen(c, WidgetTemplate.DATA_TABLE)).isEqualTo(WidgetTemplate.DATA_TABLE);
  }

  @Test
  @DisplayName("조각이 너무 많거나 음수가 섞이면 파이를 거부하고 막대로 강등한다")
  void rejectsUnreadablePie() {
    AggregateContext many = ctx(data("건", List.of(1, 2, 3, 4, 5, 6, 7, 8, 9)), true);
    assertThat(chosen(many, WidgetTemplate.PIE_CHART)).isEqualTo(WidgetTemplate.BAR_CHART);

    AggregateContext negative = ctx(data("건", List.of(5, -3, 2)), true);
    assertThat(chosen(negative, WidgetTemplate.PIE_CHART)).isEqualTo(WidgetTemplate.BAR_CHART);
  }

  @Test
  @DisplayName("점이 하나뿐이면 그림을 내지 않는다")
  void rejectsSinglePointSeries() {
    // 큰 숫자 카드는 채팅 인포그래픽에서 뺐다. 점 하나로 그릴 그래프는 없으니 아무것도 안 낸다.
    AggregateContext one = ctx(data("건", List.of(7)), true);
    assertThat(chosen(one, WidgetTemplate.LINE_CHART)).isNull();
    assertThat(chosen(one, WidgetTemplate.BAR_CHART)).isNull();
  }

  @Test
  @DisplayName("비율 지표가 아니면 PROGRESS_LIST 를 거부한다")
  void progressListNeedsRatioUnit() {
    // 거부한 뒤에는 데이터 모양이 정한다 — 두 갈래라 파이로 떨어진다.
    assertThat(chosen(ctx(data("건", List.of(1, 2)), true), WidgetTemplate.PROGRESS_LIST))
        .isEqualTo(WidgetTemplate.PIE_CHART);
    assertThat(chosen(ctx(data("%", List.of(1, 2)), true), WidgetTemplate.PROGRESS_LIST))
        .isEqualTo(WidgetTemplate.PROGRESS_LIST);
  }

  @Test
  @DisplayName("모델이 고르지 않으면 데이터 모양이 정한다")
  void fallsBackToShape() {
    // 세 갈래는 구성비로 읽는 게 낫다 — 넷~여섯은 도넛, 일곱부터 막대로 넘어간다.
    assertThat(chosen(ctx(data("건", List.of(1, 2, 3)), true), null))
        .isEqualTo(WidgetTemplate.PIE_CHART);
    assertThat(chosen(ctx(data("건", List.of(1, 2, 3, 4, 5, 6, 7, 8)), true), null))
        .isEqualTo(WidgetTemplate.BAR_CHART);
    // 축이 없으면 나눌 것이 없다.
    assertThat(chosen(ctx(data("건", List.of(1)), false), null)).isNull();
  }

  @Test
  @DisplayName("행도 합계도 없으면 그림을 내지 않는다")
  void noDataNoChart() {
    assertThat(chosen(ctx(data("건", List.of()), true), WidgetTemplate.BAR_CHART)).isNull();
  }

  @Test
  @DisplayName("채팅에서 못 쓰는 템플릿은 데이터가 맞아도 거부한다")
  void rejectsUnsupportedTemplates() {
    // 거부한 뒤에는 데이터 모양이 정한다 — 세 갈래라 파이로 떨어진다.
    AggregateContext c = ctx(data("건", List.of(1, 2, 3)), true);
    assertThat(chosen(c, WidgetTemplate.CHECKLIST)).isEqualTo(WidgetTemplate.PIE_CHART);
    assertThat(chosen(c, WidgetTemplate.GANTT_SUMMARY)).isEqualTo(WidgetTemplate.PIE_CHART);
  }
}
