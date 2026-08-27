package kr.co.axlink.project.web;

import java.time.Instant;
import java.util.UUID;

public record AssignmentResponse(
    UUID id,
    UUID projectId,
    UUID contractorOrgId,
    String contractorOrgName,
    UUID userId,
    String userName,
    String userEmail,
    String status,
    Instant assignedAt) {
}
