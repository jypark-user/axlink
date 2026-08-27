package kr.co.axlink.document.extract;

import java.nio.file.Path;
import kr.co.axlink.document.domain.UploadExt;

public interface TextExtractor {

  boolean supports(UploadExt ext);

  ExtractedText extract(Path file) throws Exception;
}
