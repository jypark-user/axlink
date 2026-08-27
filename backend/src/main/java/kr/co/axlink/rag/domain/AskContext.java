package kr.co.axlink.rag.domain;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;

public record AskContext(
    UUID conversationId,
    String question,
    Set<UUID> projectScope,
    AuthPrincipal principal,
    UUID userMessageId,
    UUID assistantMessageId,
    List<Message> history) {

  public record Message(MessageRole role, String content) {}
}
