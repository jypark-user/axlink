package kr.co.axlink.ai.port;

import com.fasterxml.jackson.databind.JsonNode;

public record ToolInvocation(String toolName, JsonNode arguments, String rawText) {

  public boolean isPresent() {
    return toolName != null && arguments != null && arguments.isObject();
  }
}
