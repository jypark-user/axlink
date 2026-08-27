package kr.co.axlink.rag.dto;

import java.util.UUID;

public record SseStartEvent(
    UUID conversationId,
    UUID userMessageId,
    UUID assistantMessageId,
    QueryRouting routing,
    int retrievedChunkCount) {}
