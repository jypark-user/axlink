package kr.co.axlink.common.error;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class GlobalExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  @ExceptionHandler(ApiException.class)
  public ResponseEntity<ErrorResponse> handleApi(ApiException e, HttpServletRequest request) {
    if (e.code().status().is5xxServerError()) {
      log.error("api error {}", e.code(), e);
    }
    return build(e.code(), e.getMessage(), e.details(), request);
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException e,
      HttpServletRequest request) {
    List<Map<String, Object>> fieldErrors = e.getBindingResult().getFieldErrors().stream()
        .map(GlobalExceptionHandler::fieldError)
        .toList();
    return build(ErrorCode.VALIDATION_FAILED, null, Map.of("fieldErrors", fieldErrors), request);
  }

  @ExceptionHandler({MissingServletRequestParameterException.class,
      MethodArgumentTypeMismatchException.class, HttpMessageNotReadableException.class,
      IllegalArgumentException.class})
  public ResponseEntity<ErrorResponse> handleBadRequest(Exception e, HttpServletRequest request) {
    return build(ErrorCode.VALIDATION_FAILED, e.getMessage(), null, request);
  }

  @ExceptionHandler(AccessDeniedException.class)
  public ResponseEntity<ErrorResponse> handleAccessDenied(AccessDeniedException e,
      HttpServletRequest request) {
    return build(ErrorCode.ROLE_FORBIDDEN, null, null, request);
  }

  @ExceptionHandler(DuplicateKeyException.class)
  public ResponseEntity<ErrorResponse> handleDuplicate(DuplicateKeyException e,
      HttpServletRequest request) {
    return build(ErrorCode.DUPLICATE_RESOURCE, null, null, request);
  }

  @ExceptionHandler(MaxUploadSizeExceededException.class)
  public ResponseEntity<ErrorResponse> handleMaxUpload(MaxUploadSizeExceededException e,
      HttpServletRequest request) {
    return build(ErrorCode.PAYLOAD_TOO_LARGE, null, null, request);
  }

  @ExceptionHandler(NoResourceFoundException.class)
  public ResponseEntity<ErrorResponse> handleNoResource(NoResourceFoundException e,
      HttpServletRequest request) {
    return build(ErrorCode.RESOURCE_NOT_FOUND, null, null, request);
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<ErrorResponse> handleFallback(Exception e, HttpServletRequest request) {
    log.error("unhandled error", e);
    return build(ErrorCode.INTERNAL_ERROR, null, null, request);
  }

  private static Map<String, Object> fieldError(FieldError error) {
    return Map.of(
        "field", error.getField(),
        "reason", error.getDefaultMessage() == null ? "올바르지 않은 값입니다."
            : error.getDefaultMessage());
  }

  private static ResponseEntity<ErrorResponse> build(ErrorCode code, String message,
      Map<String, Object> details, HttpServletRequest request) {
    return ResponseEntity.status(code.status())
        .body(ErrorResponse.of(code, message, details, request.getRequestURI()));
  }
}
