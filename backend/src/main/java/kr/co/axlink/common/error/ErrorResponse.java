package kr.co.axlink.common.error;

import java.time.Instant;
import java.util.Map;

public record ErrorResponse(
    String code,
    String message,
    Map<String, Object> details,
    String path,
    Instant timestamp) {

  public static ErrorResponse of(ErrorCode code, String message, Map<String, Object> details,
      String path) {
    return new ErrorResponse(
        code.name(),
        message == null || message.isBlank() ? code.defaultMessage() : message,
        details,
        path,
        Instant.now());
  }
}
