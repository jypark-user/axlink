package kr.co.axlink.common.error;

import java.util.Map;
import java.util.UUID;

public final class ApiExceptions {

  private ApiExceptions() {
  }

  public static ApiException validationFailed(String reason) {
    return new ApiException(ErrorCode.VALIDATION_FAILED, reason);
  }

  public static ApiException credentialsInvalid() {
    return new ApiException(ErrorCode.AUTH_CREDENTIALS_INVALID);
  }

  public static ApiException tokenExpired() {
    return new ApiException(ErrorCode.AUTH_TOKEN_EXPIRED);
  }

  public static ApiException tokenInvalid() {
    return new ApiException(ErrorCode.AUTH_TOKEN_INVALID);
  }

  public static ApiException roleForbidden() {
    return new ApiException(ErrorCode.ROLE_FORBIDDEN);
  }

  public static ApiException projectAccessDenied() {
    return new ApiException(ErrorCode.PROJECT_ACCESS_DENIED);
  }

  public static ApiException notFound(String entity, UUID id) {
    return new ApiException(ErrorCode.RESOURCE_NOT_FOUND, null,
        Map.of("entity", entity, "id", String.valueOf(id)));
  }

  public static ApiException duplicate(String entity, String naturalKey) {
    return new ApiException(ErrorCode.DUPLICATE_RESOURCE, null,
        Map.of("entity", entity, "key", naturalKey));
  }

  public static ApiException invalidTransition(Enum<?> from, Enum<?> to) {
    return new ApiException(ErrorCode.INVALID_STATE_TRANSITION, null,
        Map.of("from", enumName(from), "to", enumName(to)));
  }

  private static String enumName(Enum<?> value) {
    return value == null ? "null" : value.name();
  }

  public static ApiException projectClosed(UUID projectId) {
    return new ApiException(ErrorCode.PROJECT_CLOSED, null,
        Map.of("projectId", String.valueOf(projectId)));
  }

  public static ApiException catalogValidationFailed(String reason) {
    return new ApiException(ErrorCode.CATALOG_VALIDATION_FAILED, reason);
  }

  public static ApiException toolAuthFailed(int toolStatus, String toolMessage) {
    return new ApiException(ErrorCode.TOOL_AUTH_FAILED, null,
        Map.of("toolStatus", toolStatus, "toolMessage", String.valueOf(toolMessage)));
  }

  public static ApiException toolUnreachable(String toolMessage) {
    return new ApiException(ErrorCode.TOOL_UNREACHABLE, null,
        Map.of("toolMessage", String.valueOf(toolMessage)));
  }

  public static ApiException syncJobConflict(UUID connectionId) {
    return new ApiException(ErrorCode.SYNC_JOB_CONFLICT, null,
        Map.of("connectionId", String.valueOf(connectionId)));
  }

  public static ApiException aiUnavailable(String reason) {
    return new ApiException(ErrorCode.AI_UNAVAILABLE, reason);
  }

  public static ApiException aiToolCallFailed(String reason) {
    return new ApiException(ErrorCode.AI_TOOL_CALL_FAILED, reason);
  }

  public static ApiException internal(String reason) {
    return new ApiException(ErrorCode.INTERNAL_ERROR, reason);
  }

  public static ApiException unsupportedFileType(String reason) {
    return new ApiException(ErrorCode.UNSUPPORTED_FILE_TYPE, reason);
  }

  public static ApiException payloadTooLarge(long maxSize) {
    return new ApiException(ErrorCode.PAYLOAD_TOO_LARGE, null,
        Map.of("maxBytes", String.valueOf(maxSize)));
  }

  public static ApiException documentParseFailed(String reason) {
    return new ApiException(ErrorCode.DOCUMENT_PARSE_FAILED, reason);
  }

  public static ApiException workProductTypeRejected(String rawType) {
    return new ApiException(ErrorCode.WORK_PRODUCT_TYPE_REJECTED, null,
        Map.of("rawType", String.valueOf(rawType)));
  }
}
