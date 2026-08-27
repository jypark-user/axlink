package kr.co.axlink.ai.adapter.fake;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import kr.co.axlink.ai.port.LlmDelta;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.ai.port.LlmResponse;
import kr.co.axlink.ai.port.LlmRole;
import kr.co.axlink.ai.port.ToolInvocation;
import kr.co.axlink.ai.port.ToolRequest;

public class FakeLlmAdapter implements LlmPort {

  private static final int SUMMARY_LIMIT = 200;
  private static final int DELTA_SIZE = 24;
  private static final JsonNodeFactory NODES = JsonNodeFactory.instance;

  @Override
  public LlmResponse complete(LlmRequest request) {
    String text = answerFor(request);
    return new LlmResponse(text, request.model(), charCount(request), text.length());
  }

  @Override
  public void stream(LlmRequest request, Consumer<LlmDelta> onDelta) {
    String text = answerFor(request);
    for (int from = 0; from < text.length(); from += DELTA_SIZE) {
      int to = Math.min(from + DELTA_SIZE, text.length());
      onDelta.accept(new LlmDelta(text.substring(from, to), false));
    }
    onDelta.accept(new LlmDelta("", true));
  }

  @Override
  public ToolInvocation callTool(ToolRequest request) {
    ObjectNode arguments = argumentsFor(request.tool().parameters());
    return new ToolInvocation(request.tool().name(), arguments, arguments.toString());
  }

  private static String answerFor(LlmRequest request) {
    String question = lastContentOf(request.messages(), LlmRole.USER);
    String summary = question.strip().replaceAll("\\s+", " ");
    if (summary.length() > SUMMARY_LIMIT) {
      summary = summary.substring(0, SUMMARY_LIMIT);
    }
    return "FAKE(" + request.model() + "): " + summary + " [1]";
  }

  private static String lastContentOf(List<LlmMessage> messages, LlmRole role) {
    for (int i = messages.size() - 1; i >= 0; i--) {
      if (messages.get(i).role() == role) {
        return messages.get(i).content();
      }
    }
    return messages.get(messages.size() - 1).content();
  }

  private static int charCount(LlmRequest request) {
    int total = 0;
    for (LlmMessage message : request.messages()) {
      total += message.content().length();
    }
    return total;
  }

  private static ObjectNode argumentsFor(Map<String, Object> schema) {
    ObjectNode arguments = NODES.objectNode();
    Object properties = schema.get("properties");
    if (!(properties instanceof Map<?, ?> propertyMap)) {
      return arguments;
    }
    for (Map.Entry<?, ?> entry : propertyMap.entrySet()) {
      String name = String.valueOf(entry.getKey());
      if (entry.getValue() instanceof Map<?, ?> definition) {
        arguments.set(name, valueFor(name, definition));
      }
    }
    return arguments;
  }

  private static JsonNode valueFor(String name, Map<?, ?> definition) {
    Object enumValues = definition.get("enum");
    if (enumValues instanceof List<?> values && !values.isEmpty()) {
      return NODES.textNode(String.valueOf(values.get(0)));
    }
    Object declaredType = definition.get("type");
    String type = declaredType == null ? "string" : String.valueOf(declaredType);
    return switch (type) {
      case "integer", "number" -> NODES.numberNode(1);
      case "boolean" -> NODES.booleanNode(true);
      case "array" -> arrayFor(name, definition);
      case "object" -> NODES.objectNode();
      default -> NODES.textNode("fake-" + name);
    };
  }

  private static ArrayNode arrayFor(String name, Map<?, ?> definition) {
    ArrayNode array = NODES.arrayNode();
    if (definition.get("items") instanceof Map<?, ?> items) {
      array.add(valueFor(name, items));
    }
    return array;
  }
}
