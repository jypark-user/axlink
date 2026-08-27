package kr.co.axlink.document.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.document.domain.DocumentUploadStatus;
import kr.co.axlink.document.domain.StructuringDraftStatus;
import kr.co.axlink.integration.port.WorkProductType;
import kr.co.axlink.standard.domain.PmActivity;
import kr.co.axlink.standard.domain.RequirementPriority;
import kr.co.axlink.standard.domain.SiActivity;
import kr.co.axlink.standard.domain.WorkProductStatus;

public final class DocumentDtos {

  private DocumentDtos() {}

  /** 색인된 본문 한 조각. 전문 열람은 이 조각을 순서대로 이어 붙여 보여 준다. */
  public record DocumentChunkResponse(int index, String content) {}

  public record DocumentUploadResponse(
      UUID id, UUID projectId, String fileName, long fileSize, String mimeType,
      DocumentUploadStatus status, String uploadedBy, Instant uploadedAt,
      Integer extractedCharCount, boolean draftAvailable, UUID workProductId, String error) {}

  public record StructuringDraftResponse(
      UUID documentId, StructuringDraftStatus status, WorkProductType suggestedType,
      String rejectedTypeRaw, double confidence, String title, String version,
      LocalDate authoredDate, PmActivity pmActivity, SiActivity siActivity,
      List<DraftRequirement> requirements, Instant createdAt) {}

  public record DraftRequirement(
      int index, String code,
      @NotBlank String title, @NotBlank String body,
      @NotNull RequirementPriority priority) {}

  public record StructuringConfirmRequest(
      @NotNull WorkProductType type, @NotBlank String title, @NotBlank String version,
      LocalDate authoredDate,
      PmActivity pmActivity, SiActivity siActivity,
      @Valid @NotEmpty List<DraftRequirement> requirements,
      @NotNull WorkProductStatus workProductStatus) {}

  public record StructuringConfirmResponse(UUID workProductId, List<UUID> createdRequirementIds, int indexedChunkCount) {}
}
