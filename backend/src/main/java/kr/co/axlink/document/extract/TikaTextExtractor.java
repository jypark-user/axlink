package kr.co.axlink.document.extract;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import kr.co.axlink.document.domain.UploadExt;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.parser.AutoDetectParser;
import org.apache.tika.parser.ParseContext;
import org.apache.tika.sax.BodyContentHandler;
import org.springframework.stereotype.Component;

@Component
public class TikaTextExtractor implements TextExtractor {

  private static final Set<UploadExt> SUPPORTED = Set.of(UploadExt.PDF, UploadExt.DOCX, UploadExt.XLSX);

  @Override
  public boolean supports(UploadExt ext) {
    return SUPPORTED.contains(ext);
  }

  @Override
  public ExtractedText extract(Path file) throws Exception {
    BodyContentHandler handler = new BodyContentHandler(-1);
    Metadata metadata = new Metadata();
    try (InputStream in = Files.newInputStream(file)) {
      new AutoDetectParser().parse(in, handler, metadata, new ParseContext());
    }
    String text = handler.toString();
    Integer pageCount = pageCount(metadata);
    return new ExtractedText(text, pageCount);
  }

  private static Integer pageCount(Metadata metadata) {
    String xmpPages = metadata.get("xmpTPg:NPages");
    if (xmpPages != null && !xmpPages.isBlank()) {
      try { return Integer.parseInt(xmpPages.trim()); } catch (NumberFormatException ignore) {}
    }
    String tikaPages = metadata.get("meta:page-count");
    if (tikaPages != null && !tikaPages.isBlank()) {
      try { return Integer.parseInt(tikaPages.trim()); } catch (NumberFormatException ignore) {}
    }
    return null;
  }
}
