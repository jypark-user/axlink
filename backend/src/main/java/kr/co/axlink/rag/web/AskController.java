package kr.co.axlink.rag.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ScheduledExecutorService;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.rag.domain.AskContext;
import kr.co.axlink.rag.dto.AskRequest;
import kr.co.axlink.rag.dto.MessageFeedbackRequest;
import kr.co.axlink.rag.service.ConversationService;
import kr.co.axlink.rag.service.RagOrchestrator;
import kr.co.axlink.rag.service.SseSink;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class AskController {

  private static final Logger log = LoggerFactory.getLogger(AskController.class);
  private static final long SSE_TIMEOUT = 190_000L;

  private final ConversationService conversationService;
  private final RagOrchestrator ragOrchestrator;
  private final ProjectAccessResolver accessResolver;
  private final ObjectMapper objectMapper;
  private final ScheduledExecutorService heartbeatScheduler;
  private final TaskExecutor ragExecutor;

  public AskController(ConversationService conversationService, RagOrchestrator ragOrchestrator,
      ProjectAccessResolver accessResolver, ObjectMapper objectMapper,
      @Qualifier("sseHeartbeatScheduler") ScheduledExecutorService heartbeatScheduler,
      @Qualifier("ragExecutor") TaskExecutor ragExecutor) {
    this.conversationService = conversationService;
    this.ragOrchestrator = ragOrchestrator;
    this.accessResolver = accessResolver;
    this.objectMapper = objectMapper;
    this.heartbeatScheduler = heartbeatScheduler;
    this.ragExecutor = ragExecutor;
  }

  @PostMapping(value = "/api/conversations/{conversationId}/messages",
      produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public SseEmitter ask(@AuthenticationPrincipal AuthPrincipal principal,
      @PathVariable UUID conversationId,
      @Valid @RequestBody AskRequest request) {
    SseEmitter emitter = new SseEmitter(SSE_TIMEOUT);
    SseSink sink = new SseSink(emitter, objectMapper, heartbeatScheduler);
    emitter.onError(e -> sink.close());
    emitter.onCompletion(sink::close);

    AskContext ctx;
    try {
      Set<UUID> scope = accessResolver.resolveScope(principal,
          request.projectScope() == null ? Set.of() : request.projectScope());
      ctx = conversationService.startAsk(principal, conversationId, request.question(), scope);
    } catch (RuntimeException e) {
      sink.error(e);
      return emitter;
    }

    ragExecutor.execute(() -> ragOrchestrator.ask(ctx, sink));
    return emitter;
  }

  @PostMapping("/api/messages/{messageId}/feedback")
  public ResponseEntity<Void> feedback(@AuthenticationPrincipal AuthPrincipal principal,
      @PathVariable UUID messageId,
      @Valid @RequestBody MessageFeedbackRequest request) {
    conversationService.feedback(principal, messageId, request);
    return ResponseEntity.noContent().build();
  }
}
