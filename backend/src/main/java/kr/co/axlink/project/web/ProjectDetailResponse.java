package kr.co.axlink.project.web;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import kr.co.axlink.project.domain.ProjectStatus;
import kr.co.axlink.project.domain.SiPhase;

public record ProjectDetailResponse(
    UUID id,
    String name,
    String description,
    String contractorName,
    ProjectStatus status,
    LocalDate startDate,
    LocalDate endDate,
    SiPhase currentSiPhase,
    UUID clientOrgId,
    String clientOrgName,
    int assignmentCount,
    int connectionCount,
    UUID defaultDashboardId,
    ProjectMetrics metrics,
    Instant createdAt,
    Instant updatedAt) {
}
