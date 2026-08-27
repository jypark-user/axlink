package kr.co.axlink.org.domain;

import java.time.Instant;
import java.util.UUID;

public record AppUser(
    UUID id,
    UUID organizationId,
    String email,
    String name,
    String passwordHash,
    Role role,
    UserStatus status,
    Instant lastLoginAt,
    Instant createdAt,
    Instant updatedAt) {
}
