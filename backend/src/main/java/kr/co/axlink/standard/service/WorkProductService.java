package kr.co.axlink.standard.service;

import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.integration.port.WorkProductType;
import kr.co.axlink.project.service.ProjectWriteGuard;
import kr.co.axlink.standard.domain.HistoryEntityType;
import kr.co.axlink.standard.domain.WorkProductStatus;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.repository.WorkProductRepository;
import kr.co.axlink.standard.web.StandardDtos.EntityHistoryResponse;
import kr.co.axlink.standard.web.StandardDtos.SourceRef;
import kr.co.axlink.standard.web.StandardDtos.WorkProductChecklistResponse;
import kr.co.axlink.standard.web.StandardDtos.WorkProductDetailResponse;
import kr.co.axlink.standard.web.StandardDtos.WorkProductResponse;
import kr.co.axlink.standard.web.StandardDtos.WorkProductVersionResponse;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WorkProductService {

  private final WorkProductRepository workProductRepository;
  private final ProjectAccessResolver accessResolver;
  private final ProjectWriteGuard writeGuard;
  private final TraceQueryHelper traceQueryHelper;
  private final JdbcClient jdbc;

  public WorkProductService(WorkProductRepository workProductRepository, ProjectAccessResolver accessResolver,
      ProjectWriteGuard writeGuard, TraceQueryHelper traceQueryHelper, JdbcClient jdbc) {
    this.workProductRepository = workProductRepository;
    this.accessResolver = accessResolver;
    this.writeGuard = writeGuard;
    this.traceQueryHelper = traceQueryHelper;
    this.jdbc = jdbc;
  }

  @Transactional(readOnly = true)
  public WorkProductChecklistResponse checklist(UUID projectId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    var rows = workProductRepository.checklist(projectId);
    int approved = (int) rows.stream().filter(r -> r.status() == WorkProductStatus.APPROVED).count();
    return new WorkProductChecklistResponse(projectId, approved, rows.size(),
        rows.stream().map(WorkProductService::toResponse).toList());
  }

  @Transactional(readOnly = true)
  public WorkProductDetailResponse get(UUID workProductId, AuthPrincipal principal) {
    StandardRows.WorkProductRow row = workProductRepository.findById(workProductId)
        .orElseThrow(() -> ApiExceptions.notFound("work_product", workProductId));
    accessResolver.requireProject(principal, row.projectId());
    var versions = workProductRepository.findVersions(row.projectId(), row.type()).stream()
        .map(v -> new WorkProductVersionResponse(v.id(), v.version(), v.status(), v.approvedAt(), v.createdAt()))
        .toList();
    int chunks = workProductRepository.countChunks(workProductId);
    List<EntityHistoryResponse> hist = traceQueryHelper.history(HistoryEntityType.WORK_PRODUCT, workProductId);
    String approvedByName = row.approvedByUserId() == null ? null
        : jdbc.sql("select name from app_user where id = :id").param("id", row.approvedByUserId())
            .query(String.class).optional().orElse(null);
    return new WorkProductDetailResponse(row.id(), row.projectId(), row.type(),
        StandardLabels.workProduct(row.type()), row.title(), row.version(), row.status(),
        row.pmActivity(), row.siActivity(), row.applicable(), row.fileUri(), row.externalUrl(),
        row.approvedByUserId(), approvedByName, row.approvedAt(), row.updatedAt(),
        row.documentUploadId(), chunks, versions, hist);
  }

  @Transactional
  public UUID upsertNewVersion(UUID projectId, WorkProductType type, String version, String title,
      UUID documentUploadId, String fileUri, java.time.LocalDate authoredAt,
      kr.co.axlink.standard.domain.PmActivity pm, kr.co.axlink.standard.domain.SiActivity si,
      WorkProductStatus status) {
    writeGuard.assertWritable(projectId);
    return workProductRepository.upsertNewVersion(projectId, type, version, title, documentUploadId,
        fileUri, authoredAt, pm, si, status);
  }

  static WorkProductResponse toResponse(StandardRows.WorkProductRow r) {
    return new WorkProductResponse(r.id(), r.projectId(), r.type(), StandardLabels.workProduct(r.type()),
        r.title(), r.version(), r.status(), r.pmActivity(), r.siActivity(), r.applicable(),
        r.dueDate(), r.fileUri(), r.externalUrl(), r.approvedByUserId(), r.approvedAt(),
        r.updatedAt());
  }

  static SourceRef toSourceRef(StandardRows.WorkProductRow r) {
    return new SourceRef(r.sourceKind(), r.toolConnectionId(), r.externalId(), r.externalUrl());
  }
}
