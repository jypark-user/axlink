package kr.co.axlink.integration.adapter;

import java.util.Map;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ErrorCode;

public class ToolResourceNotFoundException extends ApiException {

  private final String toolMessage;

  public ToolResourceNotFoundException(String toolMessage) {
    super(ErrorCode.TOOL_RESOURCE_NOT_FOUND, toolMessage,
        Map.of("toolMessage", String.valueOf(toolMessage)));
    this.toolMessage = toolMessage;
  }

  public String toolMessage() {
    return toolMessage;
  }
}
