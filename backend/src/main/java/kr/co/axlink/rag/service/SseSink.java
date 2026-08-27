package kr.co.axlink.rag.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.List;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.error.ErrorResponse;
import kr.co.axlink.rag.dto.MessageSourceResponse;
import kr.co.axlink.rag.dto.SseDeltaEvent;
import kr.co.axlink.rag.dto.SseDoneEvent;
import kr.co.axlink.rag.dto.SseInfographicEvent;
import kr.co.axlink.rag.dto.SseSourcesEvent;
import kr.co.axlink.rag.dto.SseStartEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

public class SseSink {

  private static final Logger log = LoggerFactory.getLogger(SseSink.class);

  private final SseEmitter emitter;
  private final ObjectMapper objectMapper;
  private final ScheduledExecutorService heartbeatScheduler;
  private final ScheduledFuture<?> heartbeat;
  private volatile boolean closed = false;

  public SseSink(SseEmitter emitter, ObjectMapper objectMapper,
      ScheduledExecutorService heartbeatScheduler) {
    this.emitter = emitter;
    this.objectMapper = objectMapper;
    this.heartbeatScheduler = heartbeatScheduler;
    this.heartbeat = heartbeatScheduler.scheduleAtFixedRate(this::ping, 15, 15, TimeUnit.SECONDS);
  }

  public synchronized void start(SseStartEvent event) {
    send("start", event);
  }

  public synchronized void delta(String text) {
    if (closed) {
      return;
    }
    send("delta", new SseDeltaEvent(text));
  }

  public synchronized void sources(List<MessageSourceResponse> sources) {
    send("sources", new SseSourcesEvent(sources));
  }

  public synchronized void infographic(SseInfographicEvent event) {
    send("infographic", event);
  }

  public synchronized void done(SseDoneEvent event) {
    send("done", event);
    complete();
  }

  public synchronized void error(Throwable error) {
    if (closed) {
      return;
    }
    ApiException api = error instanceof ApiException ae ? ae : ApiExceptions.internal(error.getMessage());
    ErrorResponse body = ErrorResponse.of(api.code(), api.getMessage(), api.details(), "/sse");
    send("error", body);
    complete();
  }

  public boolean isClosed() {
    return closed;
  }

  public void close() {
    complete();
  }

  private void complete() {
    if (closed) {
      return;
    }
    closed = true;
    heartbeat.cancel(false);
    emitter.complete();
  }

  private void ping() {
    if (closed) {
      return;
    }
    try {
      emitter.send(SseEmitter.event().name("ping").data("{}"));
    } catch (IOException e) {
      complete();
    }
  }

  private void send(String name, Object payload) {
    if (closed) {
      return;
    }
    try {
      emitter.send(SseEmitter.event().name(name).data(objectMapper.writeValueAsString(payload)));
    } catch (IOException e) {
      log.debug("sse send failed for event {}", name, e);
      complete();
    }
  }
}
