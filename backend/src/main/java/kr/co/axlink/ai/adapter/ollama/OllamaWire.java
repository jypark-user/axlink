package kr.co.axlink.ai.adapter.ollama;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;
import java.util.Map;

public final class OllamaWire {

  private OllamaWire() {}

  @JsonInclude(JsonInclude.Include.NON_NULL)
  public record ChatRequest(
      String model,
      List<ChatMessage> messages,
      boolean stream,
      boolean think,
      List<ToolDef> tools,
      Map<String, Object> options) {}

  @JsonInclude(JsonInclude.Include.NON_NULL)
  @JsonIgnoreProperties(ignoreUnknown = true)
  public record ChatMessage(String role, String content, List<ToolCall> tool_calls) {

    public static ChatMessage of(String role, String content) {
      return new ChatMessage(role, content, null);
    }
  }

  public record ToolDef(String type, FunctionDef function) {

    public static ToolDef function(String name, String description, Map<String, Object> params) {
      return new ToolDef("function", new FunctionDef(name, description, params));
    }
  }

  public record FunctionDef(String name, String description, Map<String, Object> parameters) {}

  @JsonIgnoreProperties(ignoreUnknown = true)
  public record ToolCall(FunctionCall function) {}

  @JsonIgnoreProperties(ignoreUnknown = true)
  public record FunctionCall(String name, JsonNode arguments) {}

  @JsonIgnoreProperties(ignoreUnknown = true)
  public record ChatChunk(
      String model,
      ChatMessage message,
      boolean done,
      @JsonProperty("done_reason") String doneReason,
      @JsonProperty("prompt_eval_count") Integer promptEvalCount,
      @JsonProperty("eval_count") Integer evalCount,
      String error) {}

  public record EmbedRequest(String model, List<String> input) {}

  @JsonIgnoreProperties(ignoreUnknown = true)
  public record EmbedResponse(String model, List<List<Float>> embeddings, String error) {}
}
