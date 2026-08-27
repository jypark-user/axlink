package kr.co.axlink.project.web;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import kr.co.axlink.project.domain.ProjectStatus;
import kr.co.axlink.project.domain.SiPhase;

public record ProjectSummaryResponse(
    UUID id,
    String name,
    ProjectStatus status,
    LocalDate startDate,
    LocalDate endDate,
    SiPhase currentSiPhase,
    UUID clientOrgId,
    String clientOrgName,
    String contractorName,
    int requiredWorkProductApproved,
    int requiredWorkProductTotal,
    int openCorrectionActionCount,
    int openRiskCount,
    Instant updatedAt) {
}
