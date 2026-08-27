package kr.co.axlink.integration.adapter;

import java.util.Map;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ErrorCode;

public class ToolRateLimitedException extends ApiException {

  private final int toolStatus;
  private final String toolMessage;

  public ToolRateLimitedException(int toolStatus, String toolMessage) {
    super(ErrorCode.TOOL_UNREACHABLE, toolMessage,
        Map.of("toolStatus", toolStatus, "toolMessage", String.valueOf(toolMessage)));
    this.toolStatus = toolStatus;
    this.toolMessage = toolMessage;
  }

  public int toolStatus() {
    return toolStatus;
  }

  public String toolMessage() {
    return toolMessage;
  }
}
