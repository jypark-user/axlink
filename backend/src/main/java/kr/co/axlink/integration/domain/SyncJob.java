package kr.co.axlink.integration.domain;

import java.time.Instant;
import java.util.UUID;

public record SyncJob(
    UUID id,
    UUID toolConnectionId,
    SyncJobKind kind,
    SyncJobStatus status,
    Instant cursorFrom,
    Instant cursorTo,
    Instant startedAt,
    Instant finishedAt,
    String statsJson,
    String errorCode,
    String error,
    UUID retryOfJobId,
    Instant createdAt,
    Instant updatedAt) {
}
