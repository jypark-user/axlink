package kr.co.axlink.rag.web;

import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.rag.dto.ConversationCreateRequest;
import kr.co.axlink.rag.dto.ConversationResponse;
import kr.co.axlink.rag.dto.ConversationUpdateRequest;
import kr.co.axlink.rag.dto.MessageResponse;
import kr.co.axlink.rag.dto.SuggestedQuestionsResponse;
import kr.co.axlink.rag.service.ConversationService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

  private final ConversationService conversationService;
  private final ProjectAccessResolver accessResolver;

  public ConversationController(ConversationService conversationService,
      ProjectAccessResolver accessResolver) {
    this.conversationService = conversationService;
    this.accessResolver = accessResolver;
  }

  @GetMapping
  public PageResponse<ConversationResponse> list(@AuthenticationPrincipal AuthPrincipal principal,
      PageQuery page) {
    return conversationService.list(principal, page);
  }

  @PostMapping
  public ResponseEntity<ConversationResponse> create(@AuthenticationPrincipal AuthPrincipal principal,
      @Valid @RequestBody ConversationCreateRequest request) {
    if (request.projectScope() != null && !request.projectScope().isEmpty()) {
      accessResolver.resolveScope(principal, request.projectScope());
    }
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(conversationService.create(principal, request));
  }

  @GetMapping("/{conversationId}")
  public ConversationResponse get(@AuthenticationPrincipal AuthPrincipal principal,
      @PathVariable UUID conversationId) {
    return conversationService.get(principal, conversationId);
  }

  @PatchMapping("/{conversationId}")
  public ConversationResponse update(@AuthenticationPrincipal AuthPrincipal principal,
      @PathVariable UUID conversationId,
      @Valid @RequestBody ConversationUpdateRequest request) {
    if (request.projectScope() != null && !request.projectScope().isEmpty()) {
      accessResolver.resolveScope(principal, request.projectScope());
    }
    return conversationService.update(principal, conversationId, request);
  }

  @DeleteMapping("/{conversationId}")
  public ResponseEntity<Void> delete(@AuthenticationPrincipal AuthPrincipal principal,
      @PathVariable UUID conversationId) {
    conversationService.delete(principal, conversationId);
    return ResponseEntity.noContent().build();
  }

  @GetMapping("/{conversationId}/messages")
  public List<MessageResponse> messages(@AuthenticationPrincipal AuthPrincipal principal,
      @PathVariable UUID conversationId) {
    return conversationService.messages(principal, conversationId);
  }

  @GetMapping("/suggestions")
  public SuggestedQuestionsResponse suggestions(@AuthenticationPrincipal AuthPrincipal principal,
      @RequestParam(name = "projectIds", required = false) List<UUID> projectIds) {
    if (projectIds != null && !projectIds.isEmpty()) {
      accessResolver.resolveScope(principal, projectIds);
    }
    return conversationService.suggestions(principal, projectIds);
  }
}
