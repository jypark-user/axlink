package kr.co.axlink.project.domain;

import java.time.Instant;
import java.util.UUID;

public record ProjectInvite(
    UUID id,
    UUID projectId,
    String tokenHash,
    Instant expiresAt,
    Instant revokedAt,
    UUID createdByUserId,
    Instant createdAt) {

  public boolean usable(Instant now) {
    return revokedAt == null && expiresAt.isAfter(now);
  }
}
