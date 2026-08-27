package kr.co.axlink.integration.domain;

import java.time.Instant;
import java.util.UUID;

public record RawArtifact(
    UUID id,
    UUID toolConnectionId,
    String externalId,
    String objectKind,
    String payloadJson,
    String contentHash,
    Instant fetchedAt,
    UUID syncJobId,
    Instant createdAt) {
}
