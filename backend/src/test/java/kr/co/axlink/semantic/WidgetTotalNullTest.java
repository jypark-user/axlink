package kr.co.axlink.semantic;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetOptions;
import kr.co.axlink.semantic.domain.CatalogStatus;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.domain.MeasureValueType;
import kr.co.axlink.semantic.domain.ValidatedSpec;
import kr.co.axlink.semantic.service.WidgetDataAssembler;
import org.junit.jupiter.api.Test;

/** 집계 대상이 하나도 없으면 비율 measure 는 null 을 낸다. 숫자 카드가 여기서 죽으면 안 된다. */
class WidgetTotalNullTest {

  @Test
  void statCardKeepsNullTotalInsteadOfThrowing() {
    MeasureDef measure = new MeasureDef(UUID.randomUUID(), "issue_resolution_rate", "이슈 처리율",
        null, "issue", null, null, "round(...)", MeasureValueType.RATE_PCT, "%",
        Set.of(), Set.of(), null, null, CatalogStatus.ACTIVE);
    ValidatedSpec spec = new ValidatedSpec(WidgetTemplate.STAT_CARD, "이슈 처리율", measure,
        List.of(), List.of(), Set.of(UUID.randomUUID()),
        new WidgetOptions(null, null, null, null, null, null, null), 50);

    Map<String, Object> row = new HashMap<>();
    row.put("value", null);
    WidgetDataResponse res = new WidgetDataAssembler().assemble(spec, List.of(row), false, null);

    assertThat(res.total()).isNotNull();
    assertThat(res.total().values().get("value")).isNull();
  }
}
