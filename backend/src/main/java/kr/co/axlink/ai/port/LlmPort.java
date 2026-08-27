package kr.co.axlink.ai.port;

import java.util.function.Consumer;

public interface LlmPort {

  LlmResponse complete(LlmRequest request);

  void stream(LlmRequest request, Consumer<LlmDelta> onDelta);

  ToolInvocation callTool(ToolRequest request);
}
