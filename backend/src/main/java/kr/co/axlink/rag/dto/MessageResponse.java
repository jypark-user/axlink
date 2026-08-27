package kr.co.axlink.rag.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record MessageResponse(
    UUID id,
    UUID conversationId,
    int seq,
    String role,
    String content,
    QueryRouting routing,
    List<MessageSourceResponse> sources,
    String feedback,
    Instant createdAt,
    /** 생성 시점에 함께 보여준 인포그래픽. 없으면 null. */
    SseInfographicEvent infographic) {
}
