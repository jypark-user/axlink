package kr.co.axlink.rag.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class HybridSearchRepository {

  private final JdbcClient jdbc;

  public HybridSearchRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  @Transactional(readOnly = true)
  public List<ScoredRow> vectorSearch(float[] queryVector, List<UUID> projectIds, int limit) {
    jdbc.sql("set local hnsw.ef_search = 100").update();
    jdbc.sql("set local hnsw.iterative_scan = relaxed_order").update();
    String pids = SqlLiterals.uuidArray(projectIds);
    return jdbc.sql("""
        select id, project_id, source_type, source_id, chunk_index, content,
               embedding_model, token_count, source_title, source_uri, content_hash, meta_json,
               1 - (embedding <=> :qvec::vector) as score
          from doc_chunk
         where project_id = any(""" + pids + """
        )
         order by embedding <=> :qvec::vector
         limit :limit
        """)
        .param("qvec", VectorCodec.toLiteral(queryVector))
        .param("limit", limit)
        .query(this::mapScored).list();
  }

  @Transactional(readOnly = true)
  public List<ScoredRow> lexSearch(String queryText, List<UUID> projectIds, int limit) {
    jdbc.sql("set local pg_trgm.similarity_threshold = 0.1").update();
    String pids = SqlLiterals.uuidArray(projectIds);
    return jdbc.sql("""
        select id, project_id, source_type, source_id, chunk_index, content,
               embedding_model, token_count, source_title, source_uri, content_hash, meta_json,
               greatest(ts_rank_cd(content_tsv, plainto_tsquery('simple', :q)),
                        similarity(content, :q)) as score
          from doc_chunk
         where project_id = any(""" + pids + """
        )
           and (content_tsv @@ plainto_tsquery('simple', :q) or content % :q)
         order by score desc
         limit :limit
        """)
        .param("q", queryText)
        .param("limit", limit)
        .query(this::mapScored).list();
  }

  private ScoredRow mapScored(ResultSet rs, int n) throws SQLException {
    return new ScoredRow(
        rs.getObject("id", UUID.class),
        rs.getObject("project_id", UUID.class),
        rs.getString("source_type"),
        rs.getObject("source_id", UUID.class),
        rs.getInt("chunk_index"),
        rs.getString("content"),
        rs.getString("embedding_model"),
        (Integer) rs.getObject("token_count"),
        rs.getString("source_title"),
        rs.getString("source_uri"),
        rs.getString("content_hash"),
        rs.getString("meta_json"),
        rs.getDouble("score"));
  }

  public record ScoredRow(
      UUID id, UUID projectId, String sourceType, UUID sourceId, int chunkIndex,
      String content, String embeddingModel, Integer tokenCount, String sourceTitle,
      String sourceUri, String contentHash, String metaJson, double score) {}
}
