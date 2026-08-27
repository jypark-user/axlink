package kr.co.axlink.document.web;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.document.domain.DocumentUploadStatus;
import kr.co.axlink.document.service.DocumentUploadService;
import kr.co.axlink.document.service.StructuringConfirmService;
import kr.co.axlink.document.service.StructuringService;
import kr.co.axlink.document.web.DocumentDtos.DocumentUploadResponse;
import kr.co.axlink.document.web.DocumentDtos.StructuringConfirmRequest;
import kr.co.axlink.document.web.DocumentDtos.StructuringConfirmResponse;
import kr.co.axlink.document.web.DocumentDtos.StructuringDraftResponse;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class DocumentController {

  private final DocumentUploadService uploadService;
  private final StructuringService structuringService;
  private final StructuringConfirmService confirmService;

  public DocumentController(DocumentUploadService uploadService, StructuringService structuringService,
      StructuringConfirmService confirmService) {
    this.uploadService = uploadService;
    this.structuringService = structuringService;
    this.confirmService = confirmService;
  }

  @GetMapping("/api/projects/{projectId}/documents")
  public PageResponse<DocumentUploadResponse> list(@PathVariable UUID projectId,
      @RequestParam(required = false) DocumentUploadStatus status,
      PageQuery page, @AuthenticationPrincipal AuthPrincipal principal) {
    return uploadService.list(projectId, status, page, principal);
  }

  @PostMapping("/api/projects/{projectId}/documents")
  public ResponseEntity<DocumentUploadResponse> upload(@PathVariable UUID projectId,
      @RequestPart("file") MultipartFile file, @AuthenticationPrincipal AuthPrincipal principal) {
    DocumentUploadResponse body = uploadService.upload(projectId, file, principal);
    return ResponseEntity.accepted().body(body);
  }

  @GetMapping("/api/documents/{documentId}")
  public DocumentUploadResponse get(@PathVariable UUID documentId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return uploadService.get(documentId, principal);
  }

  @GetMapping("/api/documents/{documentId}/draft")
  public StructuringDraftResponse draft(@PathVariable UUID documentId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return structuringService.draft(documentId, principal);
  }

  @PostMapping("/api/documents/{documentId}/draft/confirm")
  public StructuringConfirmResponse confirm(@PathVariable UUID documentId,
      @Valid @RequestBody StructuringConfirmRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return confirmService.confirm(documentId, req, principal);
  }

  @PostMapping("/api/documents/{documentId}/draft/reject")
  public ResponseEntity<Void> reject(@PathVariable UUID documentId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    confirmService.reject(documentId, principal);
    return ResponseEntity.noContent().build();
  }

  @DeleteMapping("/api/documents/{documentId}")
  public ResponseEntity<Void> delete(@PathVariable UUID documentId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    uploadService.delete(documentId, principal);
    return ResponseEntity.noContent().build();
  }

  /** 색인된 본문 전문. 요약이 아니라 문서에 적힌 그대로를 쪽으로 나눠 돌려준다. */
  @GetMapping("/api/documents/{documentId}/chunks")
  public PageResponse<DocumentDtos.DocumentChunkResponse> chunks(@PathVariable UUID documentId,
      PageQuery page, @AuthenticationPrincipal AuthPrincipal principal) {
    return uploadService.chunks(documentId, page, principal);
  }

  @GetMapping("/api/documents/{documentId}/content")
  public ResponseEntity<Resource> content(@PathVariable UUID documentId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    DocumentUploadResponse meta = uploadService.get(documentId, principal);
    Resource resource = uploadService.loadContent(documentId, principal);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .header(HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=\"" + meta.fileName() + "\"")
        .body(resource);
  }
}
