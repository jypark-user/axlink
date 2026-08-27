package kr.co.axlink.auth.domain;

import java.time.Instant;
import java.util.UUID;

public record RefreshToken(
    UUID id,
    UUID appUserId,
    String tokenHash,
    Instant expiresAt,
    Instant revokedAt,
    String userAgent,
    Instant createdAt) {

  public boolean usable(Instant now) {
    return revokedAt == null && expiresAt.isAfter(now);
  }
}
