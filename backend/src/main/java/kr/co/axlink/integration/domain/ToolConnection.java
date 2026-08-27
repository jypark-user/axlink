package kr.co.axlink.integration.domain;

import java.time.Instant;
import java.util.UUID;

public record ToolConnection(
    UUID id,
    UUID projectId,
    UUID contractorOrgId,
    ToolType tool,
    String name,
    String baseUrl,
    String targetResource,
    String authEncrypted,
    String authHint,
    String mappingRulesJson,
    String webhookSecretEncrypted,
    ToolConnectionStatus status,
    Instant lastVerifiedAt,
    Instant lastSyncedAt,
    String lastSyncCursor,
    String lastError,
    Instant createdAt,
    Instant updatedAt) {
}
