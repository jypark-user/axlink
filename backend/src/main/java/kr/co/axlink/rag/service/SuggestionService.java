package kr.co.axlink.rag.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmModels;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.ai.port.ToolInvocation;
import kr.co.axlink.ai.port.ToolRequest;
import kr.co.axlink.ai.port.ToolSchema;
import kr.co.axlink.ai.prompt.Prompts;
import kr.co.axlink.ai.prompt.ToolNames;
import kr.co.axlink.rag.dto.SuggestedQuestionsResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class SuggestionService {

  private static final Logger log = LoggerFactory.getLogger(SuggestionService.class);
  private static final List<String> FALLBACK = List.of(
      "요구사항 이행률은 어떻게 되나요?",
      "현재 진행 중인 이슈를 알려주세요",
      "미제출 산출물이 있나요?",
      "최근 변경요청 현황은?");

  private final LlmPort llmPort;
  private final LlmModels llmModels;
  private final JdbcClient jdbc;

  public SuggestionService(LlmPort llmPort, LlmModels llmModels, JdbcClient jdbc) {
    this.llmPort = llmPort;
    this.llmModels = llmModels;
    this.jdbc = jdbc;
  }

  public SuggestedQuestionsResponse suggest(Set<UUID> projectIds) {
    String context = projectContext(projectIds);
    ToolSchema schema = new ToolSchema(ToolNames.SUGGEST_QUESTIONS,
        "프로젝트 상황에 맞는 질문 4개를 제안한다.", parameters());
    LlmRequest base = LlmRequest.of(llmModels.synthesis(), List.of(
        LlmMessage.system(Prompts.ROUTING_SYSTEM),
        LlmMessage.user("프로젝트 상황:\n" + context + "\n질문 4개를 제안해라.")));
    try {
      ToolInvocation invocation = llmPort.callTool(new ToolRequest(base, schema));
      List<String> questions = parseQuestions(invocation);
      return new SuggestedQuestionsResponse(questions.size() == 4 ? questions : FALLBACK);
    } catch (RuntimeException e) {
      log.warn("suggestion tool call failed, using fallback: {}", e.getMessage());
      return new SuggestedQuestionsResponse(FALLBACK);
    }
  }

  private List<String> parseQuestions(ToolInvocation invocation) {
    if (!invocation.isPresent()) {
      return FALLBACK;
    }
    JsonNode questions = invocation.arguments().path("questions");
    if (!questions.isArray()) {
      return FALLBACK;
    }
    List<String> result = new ArrayList<>();
    for (JsonNode q : questions) {
      String text = q.asText();
      if (!text.isBlank()) {
        result.add(text.strip());
      }
    }
    return result.isEmpty() ? FALLBACK : result;
  }

  private String projectContext(Set<UUID> projectIds) {
    if (projectIds == null || projectIds.isEmpty()) {
      return "전체 프로젝트";
    }
    String literal = kr.co.axlink.rag.repository.SqlLiterals.uuidArray(projectIds);
    List<String> names = jdbc.sql("select name from project where id = any(" + literal + ")")
        .query(String.class).list();
    return names.isEmpty() ? "프로젝트 없음" : String.join(", ", names);
  }

  private static Map<String, Object> parameters() {
    Map<String, Object> question = new LinkedHashMap<>();
    question.put("type", "string");
    Map<String, Object> arrayItems = new LinkedHashMap<>();
    arrayItems.put("type", question);
    Map<String, Object> props = new LinkedHashMap<>();
    props.put("questions", Map.of("type", "array", "items", arrayItems));
    Map<String, Object> schema = new LinkedHashMap<>();
    schema.put("type", "object");
    schema.put("properties", props);
    schema.put("required", List.of("questions"));
    return schema;
  }
}
