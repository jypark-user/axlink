package kr.co.axlink.rag.domain;

import java.util.List;

public record ProcessedAnswer(
    String text,
    List<SourceRef> sources,
    String finishReason) {

  public record SourceRef(
      int footnoteNo,
      DocChunk chunk,
      String snippet) {}
}
