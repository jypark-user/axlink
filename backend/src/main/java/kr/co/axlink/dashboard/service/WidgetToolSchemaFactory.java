package kr.co.axlink.dashboard.service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.co.axlink.ai.port.ToolSchema;
import kr.co.axlink.ai.prompt.ToolNames;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.semantic.service.CatalogRegistry;
import org.springframework.stereotype.Component;

@Component
public class WidgetToolSchemaFactory {

  private final CatalogRegistry registry;

  public WidgetToolSchemaFactory(CatalogRegistry registry) {
    this.registry = registry;
  }

  public ToolSchema buildWidgetSpecSchema() {
    List<String> measureKeys = registry.activeMeasures().stream().map(m -> m.key()).toList();
    List<String> dimensionKeys = registry.activeDimensions().stream().map(d -> d.key()).toList();
    List<String> templateKeys = java.util.Arrays.stream(WidgetTemplate.values())
        .map(Enum::name).toList();

    Map<String, Object> properties = new LinkedHashMap<>();
    properties.put("template", Map.of("type", "string", "enum", templateKeys,
        "description", "위젯 템플릿. 시간축 추이는 LINE_CHART, 범주 비교는 BAR_CHART, 단일 수치는 STAT_CARD"));
    properties.put("title", Map.of("type", "string", "description", "지표와 기간이 드러나는 한국어 한 줄 제목"));
    properties.put("measure", Map.of("type", "string", "enum", measureKeys,
        "description", "semantic_measure.key 중 하나. 요청에 맞는 지표가 없으면 도구를 생략한다"));
    properties.put("dimensions", Map.of(
        "type", "array",
        "items", Map.of("type", "string", "enum", dimensionKeys),
        "description", "0~2개. semantic_dimension.key"));
    properties.put("filters", Map.of(
        "type", "array",
        "items", Map.of("type", "object", "properties", Map.of(
            "field", Map.of("type", "string"),
            "op", Map.of("type", "string", "enum",
                List.of("in", "eq", "gte", "lte", "between", "in_month", "last_n_days")),
            "value", Map.of())),
        "description", "0~5개"));
    properties.put("limit", Map.of("type", "integer", "description", "최대 행 수. 기본 50"));

    Map<String, Object> schema = Map.of(
        "type", "object",
        "properties", properties,
        "required", List.of("template", "title", "measure"));
    return new ToolSchema(ToolNames.BUILD_WIDGET_SPEC,
        "자연어 요청을 대시보드 위젯 명세로 변환한다.", schema);
  }

  public ToolSchema classifyQuerySchema() {
    Map<String, Object> schema = Map.of(
        "type", "object",
        "properties", Map.of(
            "route", Map.of("type", "string",
                "enum", List.of("DOCUMENT", "AGGREGATE", "MIXED"))),
        "required", List.of("route"));
    return new ToolSchema(ToolNames.CLASSIFY_QUERY, "질의 경로를 분류한다.", schema);
  }

  public ToolSchema suggestQuestionsSchema() {
    Map<String, Object> schema = Map.of(
        "type", "object",
        "properties", Map.of(
            "questions", Map.of("type", "array",
                "items", Map.of("type", "string"))),
        "required", List.of("questions"));
    return new ToolSchema(ToolNames.SUGGEST_QUESTIONS, "질문 후보를 제안한다.", schema);
  }
}
