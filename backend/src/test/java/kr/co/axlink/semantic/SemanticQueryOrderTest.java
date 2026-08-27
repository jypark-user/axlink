package kr.co.axlink.semantic;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetOptions;
import kr.co.axlink.semantic.domain.CatalogStatus;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.DimensionValueType;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.domain.MeasureValueType;
import kr.co.axlink.semantic.domain.ValidatedSpec;
import kr.co.axlink.semantic.service.SemanticQueryBuilder;
import org.junit.jupiter.api.Test;

/** 시계열 차트가 값 순이 아니라 시간 순으로 나오는지 확인한다. */
class SemanticQueryOrderTest {

  private final SemanticQueryBuilder builder = new SemanticQueryBuilder();

  private static final MeasureDef MEASURE = new MeasureDef(
      UUID.randomUUID(), "issue_resolution_rate", "이슈 처리율", null, "issue", null, null,
      "count(*)", MeasureValueType.COUNT, "건",
      Set.of("period_month", "issue_severity"), Set.of(), "project", null, CatalogStatus.ACTIVE);

  private static final DimensionDef MONTH = new DimensionDef(
      UUID.randomUUID(), "period_month", "월", null,
      "to_char(date_trunc('month', <TIME_COL>), 'YYYY-MM')", null, null,
      DimensionValueType.TIME, CatalogStatus.ACTIVE);

  private static final DimensionDef SEVERITY = new DimensionDef(
      UUID.randomUUID(), "issue_severity", "심각도", null, "e.severity", null, null,
      DimensionValueType.CATEGORY, CatalogStatus.ACTIVE);

  private String sqlFor(List<DimensionDef> dims) {
    WidgetOptions options = new WidgetOptions(null, "desc", null, null, null, null, null);
    return builder.build(new ValidatedSpec(WidgetTemplate.LINE_CHART, "t", MEASURE, dims,
        List.of(), Set.of(UUID.randomUUID()), options, 20)).sql();
  }

  @Test
  void timeDimensionOrdersChronologically() {
    assertThat(sqlFor(List.of(MONTH))).contains("order by d0 ASC");
  }

  @Test
  void timeDimensionWinsOverCategoryDimension() {
    assertThat(sqlFor(List.of(SEVERITY, MONTH))).contains("order by d1 ASC");
  }

  @Test
  void categoryOnlyStillOrdersByValue() {
    assertThat(sqlFor(List.of(SEVERITY))).contains("order by value DESC");
  }
}
