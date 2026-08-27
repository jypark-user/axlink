package kr.co.axlink.rag.domain;

import java.util.List;
import java.util.Map;
import java.util.UUID;

public record DocChunk(
    UUID id,
    UUID projectId,
    DocSourceType sourceType,
    UUID sourceId,
    int chunkIndex,
    String content,
    String embeddingModel,
    Integer tokenCount,
    String sourceTitle,
    String sourceUri,
    String contentHash,
    Map<String, Object> metaJson) {

  public Integer pageNo() {
    return metaJson == null ? null : (Integer) metaJson.get("pageNo");
  }

  public List<String> headingPath() {
    if (metaJson == null) {
      return List.of();
    }
    Object value = metaJson.get("headingPath");
    if (value instanceof List<?> list) {
      return list.stream().map(String::valueOf).toList();
    }
    return List.of();
  }
}
