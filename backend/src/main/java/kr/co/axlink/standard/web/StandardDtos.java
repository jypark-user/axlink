package kr.co.axlink.standard.web;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.integration.port.WorkProductType;
import kr.co.axlink.standard.domain.AcceptanceStatus;
import kr.co.axlink.standard.domain.ChangeRequestStatus;
import kr.co.axlink.standard.domain.CorrectionStatus;
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

public final class StandardDtos {

  private StandardDtos() {}

  public record EntityStatusUpdateRequest(String status, String note) {}

  public record SourceRef(
      String tool,
      UUID connectionId,
      String externalId,
      String externalUrl) {}

  public record RequirementResponse(
      UUID id,
      UUID projectId,
      String code,
      String title,
      RequirementPriority priority,
      RequirementStatus status,
      String assignee,
      SourceRef source,
      boolean traceComplete,
      Instant updatedAt) {}

  public record RequirementDetailResponse(
      UUID id,
      UUID projectId,
      String code,
      String title,
      RequirementPriority priority,
      RequirementStatus status,
      String assignee,
      SourceRef source,
      boolean traceComplete,
      Instant updatedAt,
      String body,
      List<TraceLinkResponse> traceLinks,
      List<EntityHistoryResponse> history) {}

  public record IssueResponse(
      UUID id,
      UUID projectId,
      String key,
      String title,
      IssueStatus status,
      IssueSeverity severity,
      String assignee,
      Instant resolvedAt,
      SourceRef source,
      Instant updatedAt) {}

  public record WorkProductChecklistResponse(
      UUID projectId,
      int approvedCount,
      int totalCount,
      List<WorkProductResponse> items) {}

  public record WorkProductResponse(
      UUID id,
      UUID projectId,
      WorkProductType type,
      String displayName,
      String title,
      String version,
      WorkProductStatus status,
      PmActivity pmActivity,
      SiActivity siActivity,
      boolean applicable,
      java.time.LocalDate dueDate,
      String fileUri,
      String externalUrl,
      UUID approvedBy,
      Instant approvedAt,
      Instant updatedAt) {}

  public record WorkProductDetailResponse(
      UUID id,
      UUID projectId,
      WorkProductType type,
      String displayName,
      String title,
      String version,
      WorkProductStatus status,
      PmActivity pmActivity,
      SiActivity siActivity,
      boolean applicable,
      String fileUri,
      String externalUrl,
      UUID approvedBy,
      String approvedByName,
      Instant approvedAt,
      Instant updatedAt,
      UUID documentId,
      int chunkCount,
      List<WorkProductVersionResponse> versions,
      List<EntityHistoryResponse> history) {}

  public record WorkProductVersionResponse(
      UUID id,
      String version,
      WorkProductStatus status,
      Instant approvedAt,
      Instant createdAt) {}

  public record RiskResponse(
      UUID id,
      UUID projectId,
      String title,
      RiskLevel probability,
      RiskLevel impact,
      RiskLevel severity,
      String mitigation,
      RiskStatus status,
      SourceRef source,
      Instant updatedAt) {}

  public record ChangeRequestResponse(
      UUID id,
      UUID projectId,
      String code,
      String title,
      String reason,
      String impactSummary,
      ChangeRequestStatus status,
      SourceRef source,
      Instant updatedAt) {}

  public record CorrectionActionResponse(
      UUID id,
      UUID projectId,
      String code,
      String finding,
      String action,
      String owner,
      LocalDate dueDate,
      CorrectionStatus status,
      long overdueDays,
      Instant updatedAt) {}

  public record TraceLinkResponse(
      UUID id,
      UUID projectId,
      TraceEntityType fromType,
      UUID fromId,
      String fromLabel,
      TraceEntityType toType,
      UUID toId,
      String toLabel,
      TraceLinkKind linkKind,
      TraceLinkOrigin origin,
      TraceLinkStatus status,
      String externalUrl,
      Instant createdAt) {}

  public record TraceLinkCreateRequest(
      TraceEntityType fromType,
      UUID fromId,
      TraceEntityType toType,
      UUID toId,
      TraceLinkKind linkKind) {}

  public record TraceabilityRowResponse(
      UUID requirementId,
      String requirementCode,
      String requirementTitle,
      RequirementStatus requirementStatus,
      List<TraceCell> designs,
      List<TraceCell> implementsList,
      List<TraceCell> tests,
      List<TraceLinkKind> brokenAt) {}

  public record TraceCell(
      UUID targetId,
      String label,
      String externalUrl) {}

  public record ProgressRecordResponse(
      UUID id,
      UUID projectId,
      String period,
      double plannedPct,
      double actualPct,
      String summary,
      SourceRef source) {}

  public record AcceptanceRecordCreateRequest(
      String acceptedBy,
      LocalDate acceptedAt,
      String conditions,
      UUID documentId) {}

  public record AcceptanceRecordResponse(
      UUID id,
      UUID projectId,
      String acceptedBy,
      LocalDate acceptedAt,
      String conditions,
      String documentUri,
      AcceptanceStatus status,
      Instant createdAt) {}

  public record EntityHistoryResponse(
      UUID id,
      String entityType,
      UUID entityId,
      String field,
      String fromValue,
      String toValue,
      String actor,
      String actorName,
      Instant changedAt) {}
}
