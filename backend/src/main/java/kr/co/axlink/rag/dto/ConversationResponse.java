package kr.co.axlink.rag.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record ConversationResponse(
    UUID id,
    String title,
    List<UUID> projectScope,
    List<String> projectNames,
    boolean pinned,
    int messageCount,
    Instant lastMessageAt,
    Instant createdAt) {
}
