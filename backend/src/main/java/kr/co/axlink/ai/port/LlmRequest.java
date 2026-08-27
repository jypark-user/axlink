package kr.co.axlink.ai.port;

import java.util.List;
import java.util.Objects;

public record LlmRequest(
    String model,
    List<LlmMessage> messages,
    Double temperature,
    Integer maxTokens,
    boolean think) {

  public LlmRequest {
    Objects.requireNonNull(model, "model");
    messages = List.copyOf(Objects.requireNonNull(messages, "messages"));
    if (messages.isEmpty()) {
      throw new IllegalArgumentException("messages must not be empty");
    }
  }

  public static LlmRequest of(String model, List<LlmMessage> messages) {
    return new LlmRequest(model, messages, null, null, false);
  }
}
