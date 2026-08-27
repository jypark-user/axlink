package kr.co.axlink.ai.port;

import java.util.Objects;

public record LlmMessage(LlmRole role, String content) {

  public LlmMessage {
    Objects.requireNonNull(role, "role");
    Objects.requireNonNull(content, "content");
  }

  public static LlmMessage system(String content) {
    return new LlmMessage(LlmRole.SYSTEM, content);
  }

  public static LlmMessage user(String content) {
    return new LlmMessage(LlmRole.USER, content);
  }

  public static LlmMessage assistant(String content) {
    return new LlmMessage(LlmRole.ASSISTANT, content);
  }
}
