package kr.co.axlink.common.error;

import org.springframework.http.HttpStatus;

public enum ErrorCode {

  VALIDATION_FAILED(HttpStatus.BAD_REQUEST, "요청 값이 올바르지 않습니다."),
  AUTH_CREDENTIALS_INVALID(HttpStatus.UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다."),
  AUTH_TOKEN_EXPIRED(HttpStatus.UNAUTHORIZED, "인증이 만료되었습니다. 다시 로그인해 주세요."),
  AUTH_TOKEN_INVALID(HttpStatus.UNAUTHORIZED, "유효하지 않은 토큰입니다."),
  ROLE_FORBIDDEN(HttpStatus.FORBIDDEN, "이 작업을 수행할 권한이 없습니다."),
  PROJECT_ACCESS_DENIED(HttpStatus.FORBIDDEN, "해당 프로젝트에 접근할 수 없습니다."),
  RESOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "대상을 찾을 수 없습니다."),
  DUPLICATE_RESOURCE(HttpStatus.CONFLICT, "이미 존재하는 값입니다."),
  INVALID_STATE_TRANSITION(HttpStatus.CONFLICT, "허용되지 않는 상태 전이입니다."),
  PROJECT_CLOSED(HttpStatus.CONFLICT, "종료된 프로젝트는 변경할 수 없습니다."),
  CLOSURE_GATE_UNSATISFIED(HttpStatus.CONFLICT, "종료 조건을 충족하지 못했습니다."),
  WORK_PRODUCT_TYPE_REJECTED(HttpStatus.UNPROCESSABLE_ENTITY, "표준 산출물 유형이 아닙니다."),
  CATALOG_VALIDATION_FAILED(HttpStatus.UNPROCESSABLE_ENTITY, "시맨틱 카탈로그 검증에 실패했습니다."),
  TOOL_AUTH_FAILED(HttpStatus.UNPROCESSABLE_ENTITY, "도구 인증에 실패했습니다."),
  TOOL_RESOURCE_NOT_FOUND(HttpStatus.UNPROCESSABLE_ENTITY, "도구에서 대상 리소스를 찾을 수 없습니다."),
  TOOL_UNREACHABLE(HttpStatus.BAD_GATEWAY, "도구에 연결할 수 없습니다."),
  DOCUMENT_PARSE_FAILED(HttpStatus.UNPROCESSABLE_ENTITY, "문서에서 텍스트를 추출하지 못했습니다."),
  UNSUPPORTED_FILE_TYPE(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "지원하지 않는 파일 형식입니다."),
  PAYLOAD_TOO_LARGE(HttpStatus.PAYLOAD_TOO_LARGE, "업로드 용량 제한을 초과했습니다."),
  SYNC_JOB_CONFLICT(HttpStatus.CONFLICT, "이미 실행 중인 동기화 잡이 있습니다."),
  AI_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "AI 서비스에 연결할 수 없습니다."),
  AI_TOOL_CALL_FAILED(HttpStatus.BAD_GATEWAY, "AI 응답을 해석하지 못했습니다."),
  INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "요청 처리 중 오류가 발생했습니다.");

  private final HttpStatus status;
  private final String defaultMessage;

  ErrorCode(HttpStatus status, String defaultMessage) {
    this.status = status;
    this.defaultMessage = defaultMessage;
  }

  public HttpStatus status() {
    return status;
  }

  public String defaultMessage() {
    return defaultMessage;
  }
}
