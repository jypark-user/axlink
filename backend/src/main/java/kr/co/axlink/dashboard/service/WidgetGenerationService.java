package kr.co.axlink.dashboard.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmModels;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.ai.port.ToolInvocation;
import kr.co.axlink.ai.port.ToolRequest;
import kr.co.axlink.ai.prompt.Prompts;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetGenerateRequest;
import kr.co.axlink.dashboard.dto.WidgetGenerateResponse;
import kr.co.axlink.dashboard.dto.WidgetGenerationRejection;
import kr.co.axlink.dashboard.dto.WidgetSpec;
import kr.co.axlink.semantic.service.SemanticQueryExecutor;
import org.springframework.stereotype.Service;

@Service
public class WidgetGenerationService {

  private final LlmPort llmPort;
  private final LlmModels llmModels;
  private final WidgetToolSchemaFactory schemaFactory;
  private final SemanticQueryExecutor executor;

  public WidgetGenerationService(LlmPort llmPort, LlmModels llmModels,
      WidgetToolSchemaFactory schemaFactory,
      SemanticQueryExecutor executor) {
    this.llmPort = llmPort;
    this.llmModels = llmModels;
    this.schemaFactory = schemaFactory;
    this.executor = executor;
  }

  public WidgetGenerateResponse generate(WidgetGenerateRequest req, AuthPrincipal principal) {
    if (req.prompt() == null || req.prompt().isBlank()) {
      throw ApiExceptions.validationFailed("prompt 가 비어 있습니다.");
    }
    ToolInvocation invocation = callWithRetry(req);
    if (!invocation.isPresent()) {
      throw ApiExceptions.aiToolCallFailed("AI 가 도구 호출을 반환하지 않았습니다.");
    }
    WidgetSpec spec = parseSpec(invocation.arguments(), req.template());
    if (spec == null || spec.query() == null || spec.query().measure() == null) {
      return notExpressible(req.prompt());
    }
    try {
      WidgetDataResponse preview = executor.run(spec, principal, null);
      return new WidgetGenerateResponse(WidgetGenerateResponse.GENERATED, spec, preview, null);
    } catch (ApiException e) {
      if (e.code() == kr.co.axlink.common.error.ErrorCode.CATALOG_VALIDATION_FAILED) {
        return notExpressible(req.prompt());
      }
      throw e;
    }
  }

  private ToolInvocation callWithRetry(WidgetGenerateRequest req) {
    LlmRequest base = LlmRequest.of(llmModels.synthesis(),
        List.of(LlmMessage.system(Prompts.WIDGET_SYSTEM), LlmMessage.user(req.prompt())));
    ToolRequest toolRequest = new ToolRequest(base, schemaFactory.buildWidgetSpecSchema());
    ToolInvocation first = llmPort.callTool(toolRequest);
    if (first.isPresent()) {
      return first;
    }
    return llmPort.callTool(toolRequest);
  }

  private WidgetSpec parseSpec(JsonNode arguments, WidgetTemplate templateHint) {
    if (arguments == null || !arguments.isObject()) {
      return null;
    }
    JsonNode node = arguments.has("spec") ? arguments.get("spec") : arguments;
    WidgetTemplate template = templateHint;
    if (node.has("template") && !node.get("template").isNull()) {
      template = WidgetTemplate.parse(node.get("template").asText());
    }
    if (template == null) {
      return null;
    }
    String title = node.has("title") ? node.get("title").asText() : "";
    String measure = node.has("measure") ? node.get("measure").asText() : null;
    List<String> dimensions = node.has("dimensions")
        ? toTextList(node.get("dimensions")) : List.of();
    List<kr.co.axlink.dashboard.dto.WidgetFilter> filters = List.of();
    Integer limit = node.has("limit") && node.get("limit").canConvertToInt()
        ? node.get("limit").asInt() : null;
    kr.co.axlink.dashboard.dto.WidgetQuery query = new kr.co.axlink.dashboard.dto.WidgetQuery(
        measure, dimensions, filters, List.of(), limit);
    kr.co.axlink.dashboard.dto.WidgetOptions options =
        new kr.co.axlink.dashboard.dto.WidgetOptions(null, null, null, null, null, null, null);
    return new WidgetSpec(template, title, query, options);
  }

  private List<String> toTextList(JsonNode node) {
    java.util.List<String> out = new java.util.ArrayList<>();
    for (JsonNode item : node) {
      out.add(item.asText());
    }
    return out;
  }

  private WidgetGenerateResponse notExpressible(String prompt) {
    WidgetGenerationRejection rejection = new WidgetGenerationRejection(
        "카탈로그에 없는 지표를 요구했습니다.",
        List.of(),
        "ASK_IN_QNA",
        prompt);
    return new WidgetGenerateResponse(WidgetGenerateResponse.NOT_EXPRESSIBLE,
        null, null, rejection);
  }
}
