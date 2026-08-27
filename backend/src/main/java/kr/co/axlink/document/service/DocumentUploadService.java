package kr.co.axlink.document.service;

import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.config.AxLinkProperties;
import kr.co.axlink.document.domain.DocumentUpload;
import kr.co.axlink.document.domain.DocumentUploadStatus;
import kr.co.axlink.document.domain.UploadExt;
import kr.co.axlink.document.repository.DocumentUploadRepository;
import kr.co.axlink.document.repository.StructuringDraftRepository;
import kr.co.axlink.document.web.DocumentDtos.DocumentChunkResponse;
import kr.co.axlink.document.web.DocumentDtos.DocumentUploadResponse;
import kr.co.axlink.project.service.ProjectWriteGuard;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;

@Service
public class DocumentUploadService {

  private static final java.util.Map<UploadExt, String> MIME = java.util.Map.of(
      UploadExt.PDF, "application/pdf",
      UploadExt.DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      UploadExt.XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      UploadExt.HWP, "application/x-hwp",
      UploadExt.HWPX, "application/vnd.hancom.hwpx");

  private final DocumentUploadRepository uploadRepository;
  private final StructuringDraftRepository draftRepository;
  private final DocumentStorage storage;
  private final DocumentPipeline pipeline;
  private final ProjectAccessResolver accessResolver;
  private final ProjectWriteGuard writeGuard;
  private final JdbcClient jdbc;
  private final long maxUploadBytes;

  public DocumentUploadService(DocumentUploadRepository uploadRepository,
      StructuringDraftRepository draftRepository, DocumentStorage storage, DocumentPipeline pipeline,
      ProjectAccessResolver accessResolver, ProjectWriteGuard writeGuard, JdbcClient jdbc,
      AxLinkProperties props) {
    this.uploadRepository = uploadRepository;
    this.draftRepository = draftRepository;
    this.storage = storage;
    this.pipeline = pipeline;
    this.accessResolver = accessResolver;
    this.writeGuard = writeGuard;
    this.jdbc = jdbc;
    this.maxUploadBytes = props.storage().maxUploadBytes();
  }

  @Transactional
  public DocumentUploadResponse upload(UUID projectId, MultipartFile file, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    writeGuard.assertWritable(projectId);
    if (file == null || file.isEmpty()) {
      throw ApiExceptions.validationFailed("파일이 비어 있습니다.");
    }
    long size = file.getSize();
    if (size > maxUploadBytes) {
      throw ApiExceptions.payloadTooLarge(maxUploadBytes);
    }
    UploadExt ext = parseExt(file.getOriginalFilename());
    String expectedMime = MIME.get(ext);
    String storedPath;
    try {
      storedPath = storage.store(projectId, ext.name(), file.getInputStream());
    } catch (IOException e) {
      throw ApiExceptions.internal("파일 저장 실패: " + e.getMessage());
    }
    String hash = sha256(file);
    if (uploadRepository.existsByFileHash(projectId, hash)) {
      storage.delete(storedPath);
      throw ApiExceptions.duplicate("document_upload", projectId + "/" + hash);
    }
    UUID id = uploadRepository.insert(projectId, principal.userId(), file.getOriginalFilename(),
        storedPath, expectedMime, ext.name(), size, hash);
    afterCommit(() -> pipeline.process(id));
    return toResponse(load(id));
  }

  private static void afterCommit(Runnable action) {
    if (!TransactionSynchronizationManager.isSynchronizationActive()) {
      action.run();
      return;
    }
    TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
      @Override
      public void afterCommit() {
        action.run();
      }
    });
  }

  @Transactional(readOnly = true)
  public PageResponse<DocumentUploadResponse> list(UUID projectId, DocumentUploadStatus status,
      PageQuery page, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    SortSpec sort = SortSpec.parse(page.sort(), java.util.Map.of("uploadedAt", "created_at"),
        "created_at desc");
    List<DocumentUpload> rows = uploadRepository.search(projectId, status, sort, page);
    long total = uploadRepository.countSearch(projectId, status);
    return PageResponse.of(rows.stream().map(this::toResponse).toList(), page, total);
  }

  /**
   * 색인된 본문을 순서대로 돌려준다 — 요약이 아니라 문서에 적힌 그대로다.
   * 한 번에 다 내리면 큰 문서에서 화면이 버티지 못해 쪽으로 나눈다.
   */
  @Transactional(readOnly = true)
  public PageResponse<DocumentChunkResponse> chunks(UUID documentId, PageQuery page,
      AuthPrincipal principal) {
    DocumentUpload doc = load(documentId);
    accessResolver.requireProject(principal, doc.projectId());

    Long total = jdbc
        .sql("select count(*) from doc_chunk "
            + "where source_type = 'DOCUMENT_UPLOAD' and source_id = :id")
        .param("id", documentId)
        .query(Long.class)
        .single();

    List<DocumentChunkResponse> content = jdbc
        .sql("select chunk_index, content from doc_chunk "
            + "where source_type = 'DOCUMENT_UPLOAD' and source_id = :id "
            + "order by chunk_index limit :limit offset :offset")
        .param("id", documentId)
        .param("limit", page.limit())
        .param("offset", page.offset())
        .query((rs, rowNum) -> new DocumentChunkResponse(
            rs.getInt("chunk_index"), rs.getString("content")))
        .list();

    return PageResponse.of(content, page, total == null ? 0 : total);
  }

  public DocumentUploadResponse get(UUID documentId, AuthPrincipal principal) {
    DocumentUpload doc = load(documentId);
    accessResolver.requireProject(principal, doc.projectId());
    return toResponse(doc);
  }

  @Transactional
  public void delete(UUID documentId, AuthPrincipal principal) {
    DocumentUpload doc = load(documentId);
    accessResolver.requireProject(principal, doc.projectId());
    if (doc.status() == DocumentUploadStatus.CONFIRMED) {
      throw ApiExceptions.invalidTransition(doc.status(), null);
    }
    uploadRepository.delete(documentId);
    storage.delete(doc.storedPath());
  }

  @Transactional(readOnly = true)
  public org.springframework.core.io.Resource loadContent(UUID documentId, AuthPrincipal principal) {
    DocumentUpload doc = load(documentId);
    accessResolver.requireProject(principal, doc.projectId());
    return storage.load(doc.storedPath());
  }

  private DocumentUpload load(UUID id) {
    return uploadRepository.findById(id)
        .orElseThrow(() -> ApiExceptions.notFound("document", id));
  }

  DocumentUploadResponse toResponse(DocumentUpload doc) {
    Optional<kr.co.axlink.document.domain.StructuringDraft> draft =
        draftRepository.findByDocumentUploadId(doc.id());
    boolean draftAvailable = draft.isPresent()
        && (draft.get().status() == kr.co.axlink.document.domain.StructuringDraftStatus.PROPOSED
            || draft.get().status() == kr.co.axlink.document.domain.StructuringDraftStatus.MANUAL_OVERRIDE);
    UUID workProductId = draft.map(kr.co.axlink.document.domain.StructuringDraft::workProductId)
        .orElse(null);
    Integer chars = doc.extractedText() == null ? null : doc.extractedText().length();
    return new DocumentUploadResponse(doc.id(), doc.projectId(), doc.originalFilename(),
        doc.sizeBytes(), doc.contentType(), doc.status(), userName(doc.uploadedByUserId()),
        doc.createdAt(), chars, draftAvailable, workProductId, doc.error());
  }

  private String userName(UUID userId) {
    if (userId == null) {
      return null;
    }
    return jdbc.sql("select name from app_user where id = :id").param("id", userId)
        .query(String.class).optional().orElse(null);
  }

  private static UploadExt parseExt(String filename) {
    if (filename == null || filename.isBlank()) {
      throw ApiExceptions.validationFailed("파일명이 없습니다.");
    }
    int dot = filename.lastIndexOf('.');
    if (dot < 0 || dot == filename.length() - 1) {
      throw ApiExceptions.unsupportedFileType(filename);
    }
    String ext = filename.substring(dot + 1).toUpperCase();
    try {
      return UploadExt.valueOf(ext);
    } catch (IllegalArgumentException e) {
      throw ApiExceptions.unsupportedFileType(ext);
    }
  }

  private static String sha256(MultipartFile file) {
    try {
      MessageDigest md = MessageDigest.getInstance("SHA-256");
      byte[] digest = md.digest(file.getBytes());
      return HexFormat.of().formatHex(digest);
    } catch (NoSuchAlgorithmException | IOException e) {
      throw ApiExceptions.internal("해시 계산 실패: " + e.getMessage());
    }
  }
}
