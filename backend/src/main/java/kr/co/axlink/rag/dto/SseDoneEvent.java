package kr.co.axlink.rag.dto;

import java.util.UUID;

public record SseDoneEvent(
    UUID assistantMessageId,
    String finishReason,
    long elapsedMs) {}
