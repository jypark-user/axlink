package kr.co.axlink.document.service;

import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.document.domain.DocumentUpload;
import kr.co.axlink.document.domain.DocumentUploadStatus;
import kr.co.axlink.document.domain.UploadExt;
import kr.co.axlink.document.extract.ExtractedText;
import kr.co.axlink.document.extract.TextExtractor;
import kr.co.axlink.document.repository.DocumentUploadRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class DocumentPipeline {

  private static final Logger log = LoggerFactory.getLogger(DocumentPipeline.class);

  private final DocumentUploadRepository uploadRepository;
  private final DocumentStorage storage;
  private final StructuringService structuringService;
  private final List<TextExtractor> extractors;

  public DocumentPipeline(DocumentUploadRepository uploadRepository, DocumentStorage storage,
      StructuringService structuringService, List<TextExtractor> extractors) {
    this.uploadRepository = uploadRepository;
    this.storage = storage;
    this.structuringService = structuringService;
    this.extractors = extractors;
  }

  @Async("documentExecutor")
  public void process(UUID documentUploadId) {
    try {
      DocumentUpload doc = uploadRepository.findById(documentUploadId)
          .orElseThrow(() -> ApiExceptions.notFound("document", documentUploadId));
      UploadExt ext = UploadExt.valueOf(doc.fileExt());
      TextExtractor extractor = extractorFor(ext);
      Path file = storage.pathOf(doc.storedPath());
      ExtractedText extracted = extractor.extract(file);
      uploadRepository.updateExtracted(documentUploadId, extracted.text(), extracted.pageCount(),
          DocumentUploadStatus.EXTRACTED);
      structuringService.structure(documentUploadId, extracted.text(), extracted.pageCount());
    } catch (Exception e) {
      log.warn("document pipeline failed for {}", documentUploadId, e);
      uploadRepository.updateStatus(documentUploadId, DocumentUploadStatus.FAILED, e.getMessage());
    }
  }

  private TextExtractor extractorFor(UploadExt ext) {
    return extractors.stream().filter(e -> e.supports(ext)).findFirst()
        .orElseThrow(() -> ApiExceptions.unsupportedFileType(ext.name()));
  }
}
