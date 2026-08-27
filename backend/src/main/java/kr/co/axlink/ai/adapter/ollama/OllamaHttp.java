package kr.co.axlink.ai.adapter.ollama;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.Closeable;
import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.config.AxLinkProperties;

public final class OllamaHttp {

  private static final int SERVER_ERROR_ATTEMPTS = 3;
  private static final long[] SERVER_ERROR_BACKOFF_MS = {200L, 400L};

  private final HttpClient httpClient;
  private final ObjectMapper objectMapper;
  private final String baseUrl;
  private final Duration timeout;

  public OllamaHttp(
      HttpClient httpClient, ObjectMapper objectMapper, AxLinkProperties.Ollama properties) {
    this.httpClient = httpClient;
    this.objectMapper = objectMapper;
    this.baseUrl = trimTrailingSlash(properties.baseUrl());
    this.timeout = Duration.ofSeconds(properties.timeoutSeconds());
  }

  public ObjectMapper objectMapper() {
    return objectMapper;
  }

  public <T> HttpResponse<T> post(String path, Object body, HttpResponse.BodyHandler<T> handler) {
    HttpRequest request = build(path, body);
    RuntimeException last = null;
    for (int attempt = 0; attempt < SERVER_ERROR_ATTEMPTS; attempt++) {
      if (attempt > 0) {
        sleep(SERVER_ERROR_BACKOFF_MS[attempt - 1]);
      }
      HttpResponse<T> response = send(request, handler);
      int status = response.statusCode();
      if (status < 400) {
        return response;
      }
      closeQuietly(response.body());
      if (status < 500) {
        throw ApiExceptions.aiUnavailable(
            "Ollama " + path + " rejected the request with HTTP " + status);
      }
      last = ApiExceptions.aiUnavailable("Ollama " + path + " returned HTTP " + status);
    }
    throw last;
  }

  private <T> HttpResponse<T> send(HttpRequest request, HttpResponse.BodyHandler<T> handler) {
    try {
      return httpClient.send(request, handler);
    } catch (ConnectException | HttpTimeoutException e) {
      throw ApiExceptions.aiUnavailable("Ollama is not reachable at " + baseUrl + " <- " + e);
    } catch (IOException e) {
      throw ApiExceptions.aiUnavailable("Ollama call failed: " + e);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw ApiExceptions.aiUnavailable("Ollama call interrupted" + " <- " + e);
    }
  }

  private HttpRequest build(String path, Object body) {
    try {
      return HttpRequest.newBuilder(URI.create(baseUrl + path))
          .header("Content-Type", "application/json")
          .timeout(timeout)
          .POST(HttpRequest.BodyPublishers.ofByteArray(objectMapper.writeValueAsBytes(body)))
          .build();
    } catch (IOException e) {
      throw new IllegalStateException("Failed to serialize Ollama request body", e);
    }
  }

  private static void closeQuietly(Object body) {
    if (body instanceof Closeable closeable) {
      try {
        closeable.close();
      } catch (IOException ignored) {
        Thread.onSpinWait();
      }
    }
  }

  private static void sleep(long millis) {
    try {
      Thread.sleep(millis);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw ApiExceptions.aiUnavailable("Ollama retry interrupted" + " <- " + e);
    }
  }

  private static String trimTrailingSlash(String url) {
    return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
  }
}
