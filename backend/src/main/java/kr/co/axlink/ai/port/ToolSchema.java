package kr.co.axlink.ai.port;

import java.util.Map;
import java.util.Objects;

public record ToolSchema(String name, String description, Map<String, Object> parameters) {

  public ToolSchema {
    Objects.requireNonNull(name, "name");
    Objects.requireNonNull(description, "description");
    parameters = Map.copyOf(Objects.requireNonNull(parameters, "parameters"));
  }
}
