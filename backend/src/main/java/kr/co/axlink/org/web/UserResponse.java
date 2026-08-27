package kr.co.axlink.org.web;

import java.time.Instant;
import java.util.UUID;
import kr.co.axlink.org.domain.Role;
import kr.co.axlink.org.domain.UserStatus;

public record UserResponse(
    UUID id,
    UUID organizationId,
    String organizationName,
    String email,
    String name,
    Role role,
    UserStatus status,
    Instant lastLoginAt,
    Instant createdAt) {
}
