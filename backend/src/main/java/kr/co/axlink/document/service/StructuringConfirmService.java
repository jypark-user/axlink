package kr.co.axlink.document.service;

import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.document.domain.DocumentUpload;
import kr.co.axlink.document.domain.DocumentUploadStatus;
import kr.co.axlink.document.domain.StructuringDraft;
import kr.co.axlink.document.domain.StructuringDraftStatus;
import kr.co.axlink.document.repository.DocumentUploadRepository;
import kr.co.axlink.document.repository.StructuringDraftRepository;
import kr.co.axlink.document.web.DocumentDtos.DraftRequirement;
import kr.co.axlink.document.web.DocumentDtos.StructuringConfirmRequest;
import kr.co.axlink.document.web.DocumentDtos.StructuringConfirmResponse;
import kr.co.axlink.integration.port.WorkProductType;
import kr.co.axlink.project.service.ProjectWriteGuard;
import kr.co.axlink.rag.domain.DocSourceType;
import kr.co.axlink.rag.service.IndexingService;
import kr.co.axlink.standard.domain.RequirementPriority;
import kr.co.axlink.standard.domain.RequirementStatus;
import kr.co.axlink.standard.domain.WorkProductStatus;
import kr.co.axlink.standard.repository.RequirementRepository;
import kr.co.axlink.standard.repository.WorkProductRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StructuringConfirmService {

  private final DocumentUploadRepository uploadRepository;
  private final StructuringDraftRepository draftRepository;
  private final WorkProductRepository workProductRepository;
  private final RequirementRepository requirementRepository;
  private final IndexingService indexingService;
  private final ProjectAccessResolver accessResolver;
  private final ProjectWriteGuard writeGuard;
  private final Clock clock;

  public StructuringConfirmService(DocumentUploadRepository uploadRepository,
      StructuringDraftRepository draftRepository, WorkProductRepository workProductRepository,
      RequirementRepository requirementRepository, IndexingService indexingService,
      ProjectAccessResolver accessResolver, ProjectWriteGuard writeGuard, Clock clock) {
    this.uploadRepository = uploadRepository;
    this.draftRepository = draftRepository;
    this.workProductRepository = workProductRepository;
    this.requirementRepository = requirementRepository;
    this.indexingService = indexingService;
    this.accessResolver = accessResolver;
    this.writeGuard = writeGuard;
    this.clock = clock;
  }

  @Transactional
  public StructuringConfirmResponse confirm(UUID documentId, StructuringConfirmRequest req,
      AuthPrincipal principal) {
    DocumentUpload doc = uploadRepository.findById(documentId)
        .orElseThrow(() -> ApiExceptions.notFound("document", documentId));
    accessResolver.requireProject(principal, doc.projectId());
    writeGuard.assertWritable(doc.projectId());
    StructuringDraft draft = draftRepository.findByDocumentUploadId(documentId)
        .orElseThrow(() -> ApiExceptions.notFound("structuring_draft", documentId));
    if (draft.status() != StructuringDraftStatus.PROPOSED
        && draft.status() != StructuringDraftStatus.MANUAL_OVERRIDE) {
      throw ApiExceptions.invalidTransition(draft.status(), StructuringDraftStatus.CONFIRMED);
    }
    WorkProductType type = validateType(req.type());
    WorkProductStatus wpStatus = req.workProductStatus() == null ? WorkProductStatus.DRAFT : req.workProductStatus();
    UUID workProductId = workProductRepository.upsertNewVersion(doc.projectId(), type,
        req.version(), req.title(), documentId, null, req.authoredDate(),
        req.pmActivity(), req.siActivity(), wpStatus);
    List<UUID> requirementIds = new ArrayList<>();
    if (req.requirements() != null) {
      for (DraftRequirement r : req.requirements()) {
        RequirementPriority priority = r.priority() == null ? RequirementPriority.SHOULD : r.priority();
        UUID reqId = requirementRepository.insertFromDocument(doc.projectId(), workProductId,
            documentId, r.code(), r.title(), r.body(), priority, RequirementStatus.DEFINED);
        requirementIds.add(reqId);
      }
    }
    draftRepository.updateStatus(draft.id(), StructuringDraftStatus.CONFIRMED,
        principal.userId(), workProductId);
    uploadRepository.updateStatus(documentId, DocumentUploadStatus.CONFIRMED, null);
    int indexed = indexingService.reindex(DocSourceType.WORK_PRODUCT, workProductId, doc.projectId());
    for (UUID reqId : requirementIds) {
      indexingService.reindex(DocSourceType.REQUIREMENT, reqId, doc.projectId());
    }
    return new StructuringConfirmResponse(workProductId, requirementIds, indexed);
  }

  @Transactional
  public void reject(UUID documentId, AuthPrincipal principal) {
    DocumentUpload doc = uploadRepository.findById(documentId)
        .orElseThrow(() -> ApiExceptions.notFound("document", documentId));
    accessResolver.requireProject(principal, doc.projectId());
    writeGuard.assertWritable(doc.projectId());
    StructuringDraft draft = draftRepository.findByDocumentUploadId(documentId)
        .orElseThrow(() -> ApiExceptions.notFound("structuring_draft", documentId));
    if (draft.status() != StructuringDraftStatus.PROPOSED
        && draft.status() != StructuringDraftStatus.MANUAL_OVERRIDE) {
      throw ApiExceptions.invalidTransition(draft.status(), StructuringDraftStatus.REJECTED);
    }
    draftRepository.updateStatus(draft.id(), StructuringDraftStatus.REJECTED,
        principal.userId(), null);
    uploadRepository.updateStatus(documentId, DocumentUploadStatus.REJECTED, null);
  }

  static WorkProductType validateType(WorkProductType type) {
    if (type == null) {
      throw ApiExceptions.workProductTypeRejected("null");
    }
    try {
      return WorkProductType.valueOf(type.name());
    } catch (IllegalArgumentException e) {
      throw ApiExceptions.workProductTypeRejected(type.name());
    }
  }
}
