package kr.co.axlink.rag.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmModels;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.ai.port.ToolInvocation;
import kr.co.axlink.ai.port.ToolRequest;
import kr.co.axlink.ai.port.ToolSchema;
import kr.co.axlink.ai.prompt.Prompts;
import kr.co.axlink.ai.prompt.ToolNames;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.rag.domain.AskContext;
import kr.co.axlink.rag.domain.QueryRouteType;
import kr.co.axlink.rag.dto.QueryRouting;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.service.CatalogRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class QueryRouter {

  private static final Logger log = LoggerFactory.getLogger(QueryRouter.class);

  private final LlmPort llmPort;
  private final LlmModels llmModels;
  private final CatalogRegistry catalogRegistry;

  public QueryRouter(LlmPort llmPort, LlmModels llmModels, CatalogRegistry catalogRegistry) {
    this.llmPort = llmPort;
    this.llmModels = llmModels;
    this.catalogRegistry = catalogRegistry;
  }

  public QueryRouting route(String question, List<AskContext.Message> history) {
    List<MeasureDef> measures = catalogRegistry.activeMeasures();
    List<DimensionDef> dimensions = catalogRegistry.activeDimensions();
    ToolSchema schema = new ToolSchema(ToolNames.CLASSIFY_QUERY,
        "사용자 질의를 처리 경로로 분류한다.",
        parameters(measures.stream().map(MeasureDef::key).toList(),
            dimensions.stream().map(DimensionDef::key).toList(),
            glossary(measures, MeasureDef::key, MeasureDef::label, MeasureDef::description),
            glossary(dimensions, DimensionDef::key, DimensionDef::label,
                DimensionDef::description)));
    StringBuilder prompt = new StringBuilder();
    if (history != null && !history.isEmpty()) {
      prompt.append("대화 이력:\n");
      for (AskContext.Message m : history) {
        prompt.append(m.role().name()).append(": ").append(m.content()).append('\n');
      }
    }
    prompt.append("질의: ").append(question);
    LlmRequest base = LlmRequest.of(llmModels.synthesis(),
        List.of(LlmMessage.system(Prompts.ROUTING_SYSTEM), LlmMessage.user(prompt.toString())));
    try {
      ToolInvocation invocation = llmPort.callTool(new ToolRequest(base, schema));
      return parse(invocation, question);
    } catch (RuntimeException e) {
      log.warn("routing tool call failed, falling back to DOCUMENT: {}", e.getMessage());
      return QueryRouting.document(question);
    }
  }

  private QueryRouting parse(ToolInvocation invocation, String question) {
    if (!invocation.isPresent()) {
      return QueryRouting.document(question);
    }
    JsonNode args = invocation.arguments();
    QueryRouteType type = enumOf(args.path("route").asText(), QueryRouteType.DOCUMENT);
    String rewritten = textOf(args.path("rewrittenQuery"), question);
    String measureKey = validMeasureKey(args.path("measureKey"));
    if (measureKey == null && type != QueryRouteType.DOCUMENT) {
      return QueryRouting.document(rewritten);
    }
    return new QueryRouting(type, rewritten, measureKey, validDimensions(args.path("dimensions")),
        validViz(args.path("viz")));
  }

  /** 모델이 고른 그림 형태. enum 밖 값이나 NONE 은 조용히 버린다 — 서버가 다시 정한다. */
  private static WidgetTemplate validViz(JsonNode node) {
    if (node.isMissingNode() || node.isNull()) {
      return null;
    }
    String value = node.asText(null);
    if (value == null || value.isBlank() || "NONE".equalsIgnoreCase(value)) {
      return null;
    }
    try {
      return WidgetTemplate.parse(value);
    } catch (IllegalArgumentException e) {
      log.warn("routing returned unknown viz '{}', server will decide", value);
      return null;
    }
  }

  /** 카탈로그에 있는 차원만 남긴다. 축과 계열로 쓰므로 두 개까지 받는다. */
  private List<String> validDimensions(JsonNode node) {
    if (!node.isArray()) {
      return List.of();
    }
    List<String> keys = new ArrayList<>();
    for (JsonNode item : node) {
      String key = item.asText(null);
      if (key != null && !key.isBlank() && catalogRegistry.dimension(key).isPresent()
          && !keys.contains(key)) {
        keys.add(key);
      }
      if (keys.size() == 2) {
        break;
      }
    }
    return List.copyOf(keys);
  }

  private String validMeasureKey(JsonNode node) {
    if (node.isMissingNode() || node.isNull()) {
      return null;
    }
    String key = node.asText(null);
    if (key == null || key.isBlank()) {
      return null;
    }
    if (catalogRegistry.measure(key).isEmpty()) {
      log.warn("routing returned unknown measureKey '{}', falling back to DOCUMENT", key);
      return null;
    }
    return key;
  }

  /** 키 목록만 주면 모델이 key 를 글자로 추측한다. 뜻을 붙여 고르게 한다. */
  static <T> String glossary(List<T> defs, java.util.function.Function<T, String> key,
      java.util.function.Function<T, String> label,
      java.util.function.Function<T, String> description) {
    StringBuilder sb = new StringBuilder();
    for (T def : defs) {
      sb.append(key.apply(def)).append(" = ").append(label.apply(def));
      String desc = description.apply(def);
      if (desc != null && !desc.isBlank()) {
        sb.append(" · ").append(desc);
      }
      sb.append('\n');
    }
    return sb.toString().stripTrailing();
  }

  static Map<String, Object> parameters(List<String> measureKeys,
      List<String> dimensionKeys, String measureGlossary, String dimensionGlossary) {
    Map<String, Object> route = new LinkedHashMap<>();
    route.put("type", "string");
    route.put("enum", List.of("DOCUMENT", "AGGREGATE", "MIXED"));
    Map<String, Object> rewritten = new LinkedHashMap<>();
    rewritten.put("type", "string");
    Map<String, Object> measure = new LinkedHashMap<>();
    measure.put("type", "string");
    if (!measureKeys.isEmpty()) {
      measure.put("enum", measureKeys);
      measure.put("description", "집계 지표. 각 key 의 뜻은 다음과 같다.\n" + measureGlossary);
    }
    Map<String, Object> props = new LinkedHashMap<>();
    props.put("route", route);
    props.put("rewrittenQuery", rewritten);
    Map<String, Object> dimensionItem = new LinkedHashMap<>();
    dimensionItem.put("type", "string");
    if (!dimensionKeys.isEmpty()) {
      dimensionItem.put("enum", dimensionKeys);
      dimensionItem.put("description",
          "집계를 쪼갤 분류 축. 각 key 의 뜻은 다음과 같다.\n" + dimensionGlossary);
    }
    Map<String, Object> dimensions = new LinkedHashMap<>();
    dimensions.put("type", "array");
    dimensions.put("items", dimensionItem);
    dimensions.put("maxItems", 2);
    Map<String, Object> viz = new LinkedHashMap<>();
    viz.put("type", "string");
    viz.put("enum", List.of("BAR_CHART", "HORIZONTAL_BAR_CHART", "STACKED_BAR_CHART",
        "LINE_CHART", "AREA_CHART", "PIE_CHART", "DONUT_CHART", "RADAR_CHART",
        "STATUS_FLOW", "HEATMAP", "DATA_TABLE",
        "CUMULATIVE_FLOW", "PARETO", "TREEMAP", "SLOPE_CHART", "BUMP_CHART", "SPARKLINE",
        "BULLET_CHART", "CALENDAR_HEATMAP", "NONE"));
    props.put("measureKey", measure);
    props.put("dimensions", dimensions);
    props.put("viz", viz);
    Map<String, Object> schema = new LinkedHashMap<>();
    schema.put("type", "object");
    schema.put("properties", props);
    schema.put("required", List.of("route", "rewrittenQuery"));
    return schema;
  }

  private static QueryRouteType enumOf(String value, QueryRouteType fallback) {
    if (value == null || value.isBlank()) {
      return fallback;
    }
    try {
      return QueryRouteType.valueOf(value.toUpperCase());
    } catch (IllegalArgumentException e) {
      return fallback;
    }
  }

  private static String textOf(JsonNode node, String fallback) {
    if (node == null || node.isNull() || node.asText().isBlank()) {
      return fallback;
    }
    return node.asText();
  }
}
