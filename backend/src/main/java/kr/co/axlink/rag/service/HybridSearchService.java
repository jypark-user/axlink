package kr.co.axlink.rag.service;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import kr.co.axlink.ai.port.EmbeddingPort;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.rag.domain.DocChunk;
import kr.co.axlink.rag.domain.DocSourceType;
import kr.co.axlink.rag.domain.RetrievalSet;
import kr.co.axlink.rag.domain.ScoredChunk;
import kr.co.axlink.rag.repository.HybridSearchRepository;
import kr.co.axlink.rag.repository.HybridSearchRepository.ScoredRow;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class HybridSearchService {

  private static final int RRF_K = 60;

  private final HybridSearchRepository searchRepository;
  private final EmbeddingPort embeddingPort;
  private final JsonCodec json;
  private final TaskExecutor ragExecutor;

  public HybridSearchService(HybridSearchRepository searchRepository,
      EmbeddingPort embeddingPort, JsonCodec json,
      @Qualifier("ragExecutor") TaskExecutor ragExecutor) {
    this.searchRepository = searchRepository;
    this.embeddingPort = embeddingPort;
    this.json = json;
    this.ragExecutor = ragExecutor;
  }

  public RetrievalSet search(float[] queryVector, String queryText,
      Collection<UUID> projectIds, int perList, int finalLimit) {
    List<UUID> pids = List.copyOf(projectIds);
    CompletableFuture<List<ScoredRow>> vectorFuture =
        CompletableFuture.supplyAsync(
            () -> searchRepository.vectorSearch(queryVector, pids, perList), ragExecutor);
    CompletableFuture<List<ScoredRow>> lexFuture =
        CompletableFuture.supplyAsync(
            () -> searchRepository.lexSearch(queryText, pids, perList), ragExecutor);
    try {
      return fuse(vectorFuture.get(), lexFuture.get(), finalLimit);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw ApiExceptions.internal("hybrid search interrupted");
    } catch (ExecutionException e) {
      Throwable cause = e.getCause();
      if (cause instanceof ApiException ae) {
        throw ae;
      }
      throw ApiExceptions.internal("hybrid search failed: " + cause);
    }
  }

  private RetrievalSet fuse(List<ScoredRow> vector, List<ScoredRow> lex, int finalLimit) {
    Map<UUID, ChunkAccum> byId = new LinkedHashMap<>();
    for (int rank = 0; rank < vector.size(); rank++) {
      ScoredRow row = vector.get(rank);
      byId.computeIfAbsent(row.id(), k -> new ChunkAccum(row))
          .addVector(rank);
    }
    for (int rank = 0; rank < lex.size(); rank++) {
      ScoredRow row = lex.get(rank);
      byId.computeIfAbsent(row.id(), k -> new ChunkAccum(row))
          .addLex(rank);
    }
    List<ChunkAccum> accum = new ArrayList<>(byId.values());
    accum.forEach(ChunkAccum::computeFused);
    accum.sort((a, b) -> {
      int byScore = Double.compare(b.fused, a.fused);
      if (byScore != 0) {
        return byScore;
      }
      return Integer.compare(a.vectorRank, b.vectorRank);
    });
    List<ScoredChunk> fused = accum.stream().limit(finalLimit)
        .map(ChunkAccum::toScored).toList();
    return new RetrievalSet(fused);
  }

  DocChunk toChunk(ScoredRow row) {
    return new DocChunk(
        row.id(), row.projectId(), DocSourceType.valueOf(row.sourceType()),
        row.sourceId(), row.chunkIndex(), row.content(), row.embeddingModel(),
        row.tokenCount(), row.sourceTitle(), row.sourceUri(), row.contentHash(),
        json.read(row.metaJson(), Map.class));
  }

  private class ChunkAccum {
    private final ScoredRow row;
    private int vectorRank = -1;
    private int lexRank = -1;
    private double vectorScore;
    private double lexScore;
    private double fused;

    ChunkAccum(ScoredRow row) {
      this.row = row;
    }

    void addVector(int rank) {
      this.vectorRank = rank;
      this.vectorScore = row.score();
    }

    void addLex(int rank) {
      this.lexRank = rank;
      this.lexScore = row.score();
    }

    void computeFused() {
      double sum = 0.0;
      if (vectorRank >= 0) {
        sum += 1.0 / (RRF_K + vectorRank + 1);
      }
      if (lexRank >= 0) {
        sum += 1.0 / (RRF_K + lexRank + 1);
      }
      this.fused = sum;
    }

    ScoredChunk toScored() {
      return new ScoredChunk(toChunk(row), vectorScore, lexScore, vectorRank, lexRank, fused);
    }
  }
}
