package kr.co.axlink.document.domain;

import java.time.Instant;
import java.util.UUID;

public record DocumentUpload(
    UUID id, UUID projectId, UUID uploadedByUserId, String originalFilename, String storedPath,
    String contentType, String fileExt, long sizeBytes, String fileHash, String extractedText,
    Integer pageCount, DocumentUploadStatus status, String error,
    Instant createdAt, Instant updatedAt) {

  public DocumentUpload withStatus(DocumentUploadStatus next, String error, Instant updatedAt) {
    return new DocumentUpload(id, projectId, uploadedByUserId, originalFilename, storedPath,
        contentType, fileExt, sizeBytes, fileHash, extractedText, pageCount, next, error,
        createdAt, updatedAt);
  }
}
