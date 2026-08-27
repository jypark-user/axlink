package kr.co.axlink.integration.adapter;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

/**
 * 도구 REST 호출 한 자리. 응답 코드만 우리 예외로 옮기고, 나머지는 부르는 쪽이 읽는다 —
 * GitHub·Redmine 둘 다 토큰 하나에 GET 뿐이라 이 정도면 족하다.
 */
final class ToolHttp {

  private static final HttpClient CLIENT = HttpClient.newBuilder()
      .connectTimeout(Duration.ofSeconds(10))
      .followRedirects(HttpClient.Redirect.NORMAL)
      .build();
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Duration READ_TIMEOUT = Duration.ofSeconds(20);

  private ToolHttp() {
  }

  static JsonNode get(String url, Map<String, String> headers) {
    HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(url))
        .timeout(READ_TIMEOUT)
        .GET();
    headers.forEach(builder::header);

    HttpResponse<String> res;
    try {
      res = CLIENT.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new ToolUnreachableException("요청이 중단되었습니다: " + url);
    } catch (Exception e) {
      throw new ToolUnreachableException(e.getMessage() == null ? url : e.getMessage());
    }

    int status = res.statusCode();
    if (status == 401) {
      throw new ToolAuthException(status, "인증에 실패했습니다. 토큰을 확인하십시오.");
    }
    if (status == 403) {
      // GitHub 는 사용량 초과도 403 으로 준다 — 남은 횟수가 0 이면 사용량 문제로 본다.
      String remaining = res.headers().firstValue("x-ratelimit-remaining").orElse(null);
      if ("0".equals(remaining)) {
        throw new ToolRateLimitedException(status, "도구 사용량 한도에 걸렸습니다.");
      }
      throw new ToolAuthException(status, "권한이 없습니다.");
    }
    if (status == 404) {
      throw new ToolResourceNotFoundException("대상을 찾지 못했습니다: " + url);
    }
    if (status == 429) {
      throw new ToolRateLimitedException(status, "요청이 너무 잦습니다.");
    }
    if (status >= 400) {
      throw new ToolUnreachableException("도구가 " + status + " 로 응답했습니다.");
    }

    try {
      return MAPPER.readTree(res.body());
    } catch (Exception e) {
      throw new ToolUnreachableException("응답을 읽지 못했습니다: " + e.getMessage());
    }
  }

  /** 끝의 빗금을 정리해 뒤에 경로를 붙이기 좋게 만든다. */
  static String base(String baseUrl) {
    if (baseUrl == null || baseUrl.isBlank()) {
      throw new ToolUnreachableException("주소가 비어 있습니다.");
    }
    return baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
  }
}
