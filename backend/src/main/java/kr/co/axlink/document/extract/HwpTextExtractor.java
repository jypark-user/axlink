package kr.co.axlink.document.extract;

import java.nio.file.Path;
import java.util.Set;
import kr.co.axlink.document.domain.UploadExt;
import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractMethod;
import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.reader.HWPXReader;
import kr.dogfoot.hwpxlib.tool.textextractor.TextMarks;
import org.springframework.stereotype.Component;

@Component
public class HwpTextExtractor implements TextExtractor {

  private static final Set<UploadExt> SUPPORTED = Set.of(UploadExt.HWP, UploadExt.HWPX);

  @Override
  public boolean supports(UploadExt ext) {
    return SUPPORTED.contains(ext);
  }

  @Override
  public ExtractedText extract(Path file) throws Exception {
    String ext = extOf(file);
    String text;
    if (UploadExt.HWPX.name().equalsIgnoreCase(ext)) {
      HWPXFile hwpx = HWPXReader.fromFile(file.toFile());
      text = kr.dogfoot.hwpxlib.tool.textextractor.TextExtractor.extract(hwpx,
          kr.dogfoot.hwpxlib.tool.textextractor.TextExtractMethod
              .InsertControlTextBetweenParagraphText,
          false, new TextMarks());
    } else {
      HWPFile hwp = HWPReader.fromFile(file.toFile());
      text = kr.dogfoot.hwplib.tool.textextractor.TextExtractor.extract(
          hwp, TextExtractMethod.InsertControlTextBetweenParagraphText);
    }
    return new ExtractedText(text, null);
  }

  private static String extOf(Path file) {
    String name = file.getFileName().toString();
    int dot = name.lastIndexOf('.');
    return dot < 0 ? "" : name.substring(dot + 1).toUpperCase();
  }
}
