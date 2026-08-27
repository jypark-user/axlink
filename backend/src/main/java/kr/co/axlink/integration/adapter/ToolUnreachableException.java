package kr.co.axlink.integration.adapter;

import java.util.Map;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ErrorCode;

public class ToolUnreachableException extends ApiException {

  private final String toolMessage;

  public ToolUnreachableException(String toolMessage) {
    super(ErrorCode.TOOL_UNREACHABLE, toolMessage,
        Map.of("toolMessage", String.valueOf(toolMessage)));
    this.toolMessage = toolMessage;
  }

  public String toolMessage() {
    return toolMessage;
  }
}
