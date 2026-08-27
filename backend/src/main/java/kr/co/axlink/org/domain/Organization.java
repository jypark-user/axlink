package kr.co.axlink.org.domain;

import java.time.Instant;
import java.util.UUID;

public record Organization(
    UUID id,
    String name,
    OrgType type,
    String businessNo,
    OrgStatus status,
    Instant createdAt,
    Instant updatedAt) {
}
