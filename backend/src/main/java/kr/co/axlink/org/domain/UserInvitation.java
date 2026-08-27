package kr.co.axlink.org.domain;

import java.time.Instant;
import java.util.UUID;

public record UserInvitation(
    UUID id,
    UUID appUserId,
    String tokenHash,
    Instant expiresAt,
    Instant acceptedAt,
    UUID invitedByUserId,
    Instant createdAt) {

  public boolean usable(Instant now) {
    return acceptedAt == null && expiresAt.isAfter(now);
  }
}
