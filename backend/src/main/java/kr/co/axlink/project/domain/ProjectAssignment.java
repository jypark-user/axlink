package kr.co.axlink.project.domain;

import java.time.Instant;
import java.util.UUID;

public record ProjectAssignment(
    UUID id,
    UUID projectId,
    UUID contractorOrgId,
    UUID userId,
    AssignmentStatus status,
    UUID assignedByUserId,
    Instant revokedAt,
    Instant createdAt,
    Instant updatedAt) {
}
