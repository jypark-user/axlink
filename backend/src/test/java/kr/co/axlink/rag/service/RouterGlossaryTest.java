package kr.co.axlink.rag.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import kr.co.axlink.semantic.domain.CatalogStatus;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.DimensionValueType;
import org.junit.jupiter.api.Test;

/** 라우터가 key 만 던지지 않고 뜻까지 붙여 보내는지 본다. */
class RouterGlossaryTest {

  private static DimensionDef dim(String key, String label, String description) {
    return new DimensionDef(null, key, label, description, "x", null, null,
        DimensionValueType.CATEGORY, CatalogStatus.ACTIVE);
  }

  @Test
  void glossaryJoinsLabelAndSkipsBlankDescription() {
    String text = QueryRouter.glossary(
        List.of(dim("severity", "심각도", "이슈 등급"), dim("assignee", "담당자", null)),
        DimensionDef::key, DimensionDef::label, DimensionDef::description);
    assertThat(text).isEqualTo("severity = 심각도 · 이슈 등급\nassignee = 담당자");
  }

  @Test
  void schemaCarriesGlossaryIntoMeasureAndDimension() {
    Map<String, Object> schema =
        QueryRouter.parameters(List.of("issue_open_count"), List.of("severity"),
            "issue_open_count = 미해결 이슈 건수", "severity = 심각도");
    Map<?, ?> props = (Map<?, ?>) schema.get("properties");
    Map<?, ?> measure = (Map<?, ?>) props.get("measureKey");
    Map<?, ?> items = (Map<?, ?>) ((Map<?, ?>) props.get("dimensions")).get("items");
    assertThat((String) measure.get("description")).contains("미해결 이슈 건수");
    assertThat((String) items.get("description")).contains("심각도");
  }
}
