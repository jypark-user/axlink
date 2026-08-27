package kr.co.axlink.project.domain;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public record Project(
    UUID id,
    UUID clientOrgId,
    String name,
    LocalDate startDate,
    LocalDate endDate,
    String description,
    String contractorName,
    ProjectStatus status,
    SiPhase currentSiPhase,
    Instant closedAt,
    Instant createdAt,
    Instant updatedAt) {
}
