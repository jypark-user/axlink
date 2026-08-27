package kr.co.axlink.rag.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.rag.domain.AskContext;
import kr.co.axlink.rag.domain.MessageRole;
import kr.co.axlink.rag.dto.ConversationCreateRequest;
import kr.co.axlink.rag.dto.ConversationResponse;
import kr.co.axlink.rag.dto.ConversationUpdateRequest;
import kr.co.axlink.rag.dto.MessageFeedbackRequest;
import kr.co.axlink.rag.dto.MessageResponse;
import kr.co.axlink.rag.dto.MessageSourceResponse;
import kr.co.axlink.rag.dto.QueryRouting;
import kr.co.axlink.rag.dto.SseInfographicEvent;
import kr.co.axlink.rag.dto.SuggestedQuestionsResponse;
import kr.co.axlink.rag.repository.ConversationRepository;
import kr.co.axlink.rag.repository.RagRows.ConversationRow;
import kr.co.axlink.rag.repository.RagRows.MessageRow;
import kr.co.axlink.rag.repository.RagRows.MessageSourceRow;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConversationService {

  private static final Logger log = LoggerFactory.getLogger(ConversationService.class);

  private final ConversationRepository conversationRepository;
  private final SuggestionService suggestionService;
  private final JsonCodec json;

  public ConversationService(ConversationRepository conversationRepository,
      SuggestionService suggestionService, JsonCodec json) {
    this.conversationRepository = conversationRepository;
    this.suggestionService = suggestionService;
    this.json = json;
  }

  public PageResponse<ConversationResponse> list(AuthPrincipal principal, PageQuery page) {
    List<ConversationRow> rows = conversationRepository.list(principal.userId(),
        page.offset(), page.limit());
    long total = conversationRepository.count(principal.userId());
    List<ConversationResponse> content = rows.stream().map(r -> toResponse(r, List.of())).toList();
    return PageResponse.of(content, page, total);
  }

  @Transactional
  public ConversationResponse create(AuthPrincipal principal, ConversationCreateRequest request) {
    String title = request.title() == null || request.title().isBlank()
        ? "새 대화" : request.title();
    List<UUID> scope = request.projectScope() == null ? List.of() : request.projectScope();
    UUID id = conversationRepository.create(principal.userId(), title, scope);
    ConversationRow row = conversationRepository.find(id).orElseThrow();
    return toResponse(row, scope);
  }

  public ConversationResponse get(AuthPrincipal principal, UUID id) {
    ConversationRow row = own(principal, id);
    return toResponse(row, row.projectScope());
  }

  @Transactional
  public ConversationResponse update(AuthPrincipal principal, UUID id,
      ConversationUpdateRequest request) {
    ConversationRow row = own(principal, id);
    conversationRepository.update(id,
        request.title(),
        request.pinned(),
        request.projectScope());
    ConversationRow updated = conversationRepository.find(id).orElseThrow();
    return toResponse(updated, updated.projectScope());
  }

  @Transactional
  public void delete(AuthPrincipal principal, UUID id) {
    own(principal, id);
    conversationRepository.softDelete(id);
  }

  @Transactional
  public UserMessage appendUserMessage(UUID conversationId, String content) {
    int seq = conversationRepository.nextSeq(conversationId);
    UUID id = conversationRepository.insertUserMessage(conversationId, seq, content);
    conversationRepository.touchConversation(conversationId);
    return new UserMessage(id, seq);
  }

  @Transactional
  public AskContext startAsk(AuthPrincipal principal, UUID conversationId, String question,
      Set<UUID> projectScope) {
    own(principal, conversationId);
    List<AskContext.Message> history = conversationRepository.recentHistory(conversationId, 3);
    UserMessage userMessage = appendUserMessage(conversationId, question);
    UUID assistantMessageId = UUID.randomUUID();
    return new AskContext(conversationId, question, projectScope, principal,
        userMessage.id(), assistantMessageId, history);
  }

  public record UserMessage(UUID id, int seq) {}

  public List<MessageResponse> messages(AuthPrincipal principal, UUID conversationId) {
    own(principal, conversationId);
    List<MessageRow> rows = conversationRepository.messages(conversationId);
    List<UUID> messageIds = rows.stream().map(MessageRow::id).toList();
    Map<UUID, List<MessageSourceRow>> sourcesByMessage =
        conversationRepository.sourcesByMessage(messageIds);
    List<MessageResponse> result = new ArrayList<>();
    for (MessageRow m : rows) {
      List<MessageSourceRow> srcs = sourcesByMessage.getOrDefault(m.id(), List.of());
      result.add(toMessageResponse(m, srcs));
    }
    return result;
  }

  @Transactional
  public void feedback(AuthPrincipal principal, UUID messageId, MessageFeedbackRequest request) {
    MessageRow row = conversationRepository.findMessage(messageId)
        .orElseThrow(() -> ApiExceptions.notFound("message", messageId));
    own(principal, row.conversationId());
    conversationRepository.setFeedback(messageId, request.feedback());
  }

  public SuggestedQuestionsResponse suggestions(AuthPrincipal principal, List<UUID> projectIds) {
    return suggestionService.suggest(projectIds == null ? Set.of()
        : Set.copyOf(projectIds));
  }

  private ConversationRow own(AuthPrincipal principal, UUID id) {
    ConversationRow row = conversationRepository.find(id).orElse(null);
    conversationRepository.requireOwned(row, principal.userId());
    return row;
  }

  private ConversationResponse toResponse(ConversationRow row, List<UUID> scope) {
    int messageCount = conversationRepository.messageCount(row.id());
    List<String> names = scope == null || scope.isEmpty()
        ? List.of() : conversationRepository.projectNames(scope);
    return new ConversationResponse(
        row.id(), row.title(), row.projectScope(), names, row.pinned(),
        messageCount, row.lastMessageAt(), row.createdAt());
  }

  private MessageResponse toMessageResponse(MessageRow m, List<MessageSourceRow> srcs) {
    QueryRouting routing = m.routeType() == null && m.role() == MessageRole.USER
        ? null : new QueryRouting(m.routeType(), m.rewrittenQuery(), m.measureKey(), List.of(), null);
    List<MessageSourceResponse> sources = srcs.stream().map(this::toSourceResponse).toList();
    return new MessageResponse(
        m.id(), m.conversationId(), m.seq(), m.role().name(),
        m.content(), routing, sources,
        m.feedback() == null ? null : m.feedback().name(),
        m.createdAt(), infographicOf(m));
  }

  /**
   * 저장된 스냅샷을 되살린다. 깨진 JSON 때문에 대화 전체가 안 열리는 쪽이 더 나쁘므로
   * 복원에 실패하면 그림만 버린다.
   */
  private SseInfographicEvent infographicOf(MessageRow m) {
    if (m.infographicJson() == null || m.infographicJson().isBlank()) {
      return null;
    }
    try {
      return json.read(m.infographicJson(), SseInfographicEvent.class);
    } catch (RuntimeException e) {
      log.warn("infographic restore failed for message {}: {}", m.id(), e.getMessage());
      return null;
    }
  }

  private MessageSourceResponse toSourceResponse(MessageSourceRow s) {
    return new MessageSourceResponse(
        s.footnoteNo(), s.docChunkId(), s.sourceType().name(), s.sourceId(),
        s.sourceTitle(), s.projectId(), s.projectName(), s.snippet(),
        s.externalUrl(), null, s.pageNo());
  }
}
