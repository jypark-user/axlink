package kr.co.axlink.rag.domain;

public record ScoredChunk(
    DocChunk chunk,
    double vectorScore,
    double lexScore,
    int vectorRank,
    int lexRank,
    double fusedScore) {

  public static ScoredChunk vector(DocChunk chunk, double score, int rank) {
    return new ScoredChunk(chunk, score, 0.0, rank, -1, 0.0);
  }

  public static ScoredChunk lex(DocChunk chunk, double score, int rank) {
    return new ScoredChunk(chunk, 0.0, score, -1, rank, 0.0);
  }
}
