package kr.co.axlink.rag.domain;

import java.util.List;

public record RetrievalSet(List<ScoredChunk> fused) {

  public static final RetrievalSet EMPTY = new RetrievalSet(List.of());

  public int size() {
    return fused == null ? 0 : fused.size();
  }

  public boolean isEmpty() {
    return size() == 0;
  }

  public List<DocChunk> chunks() {
    if (isEmpty()) {
      return List.of();
    }
    return fused.stream().map(ScoredChunk::chunk).toList();
  }

  public DocChunk chunkAt(int index) {
    return fused.get(index).chunk();
  }
}
