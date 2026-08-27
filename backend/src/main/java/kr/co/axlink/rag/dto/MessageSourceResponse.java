package kr.co.axlink.rag.dto;

import java.util.UUID;

public record MessageSourceResponse(
    int footnoteNo,
    UUID docChunkId,
    String sourceType,
    UUID sourceId,
    String sourceLabel,
    UUID projectId,
    String projectName,
    String snippet,
    String externalUrl,
    String documentUrl,
    Integer pageNo) {
}
