package kr.co.axlink.rag.domain;

import java.util.List;
import java.util.Map;

public record ChunkDraft(
    String content,
    int tokenCount,
    List<String> headingPath,
    Integer pageNo,
    String contentHash,
    Map<String, Object> meta) {
}
