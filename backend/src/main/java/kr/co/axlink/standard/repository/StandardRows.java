package kr.co.axlink.standard.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import kr.co.axlink.integration.port.WorkProductType;
import kr.co.axlink.standard.domain.AcceptanceStatus;
import kr.co.axlink.standard.domain.ChangeRequestStatus;
import kr.co.axlink.standard.domain.CodeChangeKind;
import kr.co.axlink.standard.domain.CodeChangeState;
import kr.co.axlink.standard.domain.CorrectionStatus;
import kr.co.axlink.standard.domain.HistoryEntityType;
import kr.co.axlink.standard.domain.IssueSeverity;
import kr.co.axlink.standard.domain.IssueStatus;
import kr.co.axlink.standard.domain.PmActivity;
import kr.co.axlink.standard.domain.RequirementPriority;
import kr.co.axlink.standard.domain.RequirementStatus;
import kr.co.axlink.standard.domain.RiskLevel;
import kr.co.axlink.standard.domain.RiskStatus;
import kr.co.axlink.standard.domain.SiActivity;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.domain.TraceLinkKind;
import kr.co.axlink.standard.domain.TraceLinkOrigin;
import kr.co.axlink.standard.domain.TraceLinkStatus;
import kr.co.axlink.standard.domain.WorkProductStatus;

public final class StandardRows {

  private StandardRows() {}

  public record RequirementRow(
      UUID id, UUID projectId, String code, String title, String body,
      RequirementPriority priority, RequirementStatus status, UUID workProductId,
      UUID documentUploadId, String assignee, UUID toolConnectionId, String externalId,
      String externalUrl, String sourceKind, Instant sourceCreatedAt, Instant sourceUpdatedAt,
      Instant createdAt, Instant updatedAt) {

    public RequirementRow withStatus(RequirementStatus next, Instant updatedAt) {
      return new RequirementRow(id, projectId, code, title, body, priority, next, workProductId,
          documentUploadId, assignee, toolConnectionId, externalId, externalUrl, sourceKind,
          sourceCreatedAt, sourceUpdatedAt, createdAt, updatedAt);
    }
  }

  public record IssueRow(
      UUID id, UUID projectId, String issueKey, String title, String body,
      IssueStatus status, IssueSeverity severity, String assignee,
      Instant sourceCreatedAt, Instant sourceUpdatedAt, Instant resolvedAt,
      UUID toolConnectionId, String externalId, String externalUrl, String sourceKind,
      Instant createdAt, Instant updatedAt) {}

  public record WorkProductRow(
      UUID id, UUID projectId, WorkProductType type, String version, String title,
      WorkProductStatus status, boolean applicable, boolean isCurrent,
      PmActivity pmActivity, SiActivity siActivity, UUID documentUploadId, String fileUri,
      LocalDate authoredAt, LocalDate dueDate, Instant submittedAt, UUID approvedByUserId,
      Instant approvedAt, String rejectReason, UUID toolConnectionId, String externalId,
      String externalUrl, String sourceKind, Instant createdAt, Instant updatedAt) {}

  public record RiskRow(
      UUID id, UUID projectId, String title, String body,
      RiskLevel probability, RiskLevel impact, RiskLevel severity, String mitigation,
      String owner, RiskStatus status, LocalDate identifiedAt, Instant closedAt,
      UUID toolConnectionId, String externalId, String externalUrl, String sourceKind,
      Instant createdAt, Instant updatedAt) {}

  public record CodeChangeRow(
      UUID id, UUID projectId, CodeChangeKind kind, String title, String refName,
      CodeChangeState state, String author, Instant occurredAt, UUID workProductId,
      UUID toolConnectionId, String externalId, String externalUrl, String sourceKind,
      Instant createdAt, Instant updatedAt) {}

  public record TraceLinkRow(
      UUID id, UUID projectId,
      TraceEntityType fromType, UUID fromId,
      TraceEntityType toType, UUID toId,
      TraceLinkKind linkKind, TraceLinkOrigin origin, TraceLinkStatus status,
      UUID createdByUserId, Instant createdAt, Instant updatedAt) {}

  public record ChangeRequestRow(
      UUID id, UUID projectId, String code, String title, String reason, String impactSummary,
      ChangeRequestStatus status, UUID requestedByUserId, UUID decidedByUserId,
      Instant requestedAt, Instant decidedAt, Instant appliedAt,
      Instant createdAt, Instant updatedAt) {}

  public record CorrectionActionRow(
      UUID id, UUID projectId, String code, String finding, String action, String owner,
      LocalDate dueDate, CorrectionStatus status, UUID sourceWorkProductId, Instant doneAt,
      UUID toolConnectionId, String externalId, String externalUrl, String sourceKind,
      Instant createdAt, Instant updatedAt) {}

  public record ProgressRecordRow(
      UUID id, UUID projectId, LocalDate periodStart, LocalDate periodEnd,
      double plannedPct, double actualPct, String summary,
      UUID toolConnectionId, String externalId, String externalUrl, String sourceKind,
      Instant createdAt, Instant updatedAt) {}

  public record AcceptanceRow(
      UUID id, UUID projectId, UUID acceptedByUserId, Instant acceptedAt, String conditions,
      UUID workProductId, AcceptanceStatus status, Instant voidedAt, Instant createdAt,
      Instant updatedAt) {}

  public record EntityHistoryRow(
      UUID id, HistoryEntityType entityType, UUID entityId, UUID projectId, String field,
      String fromValue, String toValue, Instant changedAt, String actor, Instant createdAt) {}

  public record UpsertOutcome(UUID id, boolean inserted, String currentStatus) {}
}
