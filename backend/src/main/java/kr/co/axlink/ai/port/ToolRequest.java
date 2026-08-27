package kr.co.axlink.ai.port;

import java.util.Objects;

public record ToolRequest(LlmRequest base, ToolSchema tool) {

  public ToolRequest {
    Objects.requireNonNull(base, "base");
    Objects.requireNonNull(tool, "tool");
  }
}
