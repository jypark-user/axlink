package kr.co.axlink.rag.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.rag.domain.DocChunk;
import kr.co.axlink.rag.domain.DocSourceType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class DocChunkRepository {

  private final JdbcClient jdbc;
  private final JsonCodec json;

  public DocChunkRepository(JdbcClient jdbc, JsonCodec json) {
    this.jdbc = jdbc;
    this.json = json;
  }

  public void insert(DocChunk chunk, float[] embedding) {
    Map<String, Object> meta = chunk.metaJson() == null ? Map.of() : chunk.metaJson();
    jdbc.sql("""
        insert into doc_chunk (project_id, source_type, source_id, chunk_index, content,
                               embedding, embedding_model, token_count, source_title,
                               source_uri, content_hash, meta_json)
        values (:pid, :st, :sid, :ci, :content, :emb::vector, :model, :tc, :title,
                :uri, :hash, :meta::jsonb)
        """)
        .param("pid", chunk.projectId())
        .param("st", chunk.sourceType().name())
        .param("sid", chunk.sourceId())
        .param("ci", chunk.chunkIndex())
        .param("content", chunk.content())
        .param("emb", VectorCodec.toLiteral(embedding))
        .param("model", chunk.embeddingModel())
        .param("tc", chunk.tokenCount())
        .param("title", chunk.sourceTitle())
        .param("uri", chunk.sourceUri())
        .param("hash", chunk.contentHash())
        .param("meta", json.write(meta))
        .update();
  }

  public int deleteBySource(DocSourceType type, UUID sourceId) {
    return jdbc.sql("delete from doc_chunk where source_type = :st and source_id = :sid")
        .param("st", type.name())
        .param("sid", sourceId)
        .update();
  }

  public Optional<DocChunk> find(UUID id) {
    return jdbc.sql(chunkSql("where c.id = :id"))
        .param("id", id)
        .query(this::mapChunk).optional();
  }

  public List<DocChunk> findBySource(DocSourceType type, UUID sourceId) {
    return jdbc.sql(chunkSql("where c.source_type = :st and c.source_id = :sid order by c.chunk_index"))
        .param("st", type.name())
        .param("sid", sourceId)
        .query(this::mapChunk).list();
  }

  private String chunkSql(String where) {
    return """
        select c.id, c.project_id, c.source_type, c.source_id, c.chunk_index, c.content,
               c.embedding_model, c.token_count, c.source_title, c.source_uri,
               c.content_hash, c.meta_json
          from doc_chunk c
        """ + where;
  }

  DocChunk mapChunk(ResultSet rs, int n) throws SQLException {
    return new DocChunk(
        rs.getObject("id", UUID.class),
        rs.getObject("project_id", UUID.class),
        DocSourceType.valueOf(rs.getString("source_type")),
        rs.getObject("source_id", UUID.class),
        rs.getInt("chunk_index"),
        rs.getString("content"),
        rs.getString("embedding_model"),
        (Integer) rs.getObject("token_count"),
        rs.getString("source_title"),
        rs.getString("source_uri"),
        rs.getString("content_hash"),
        json.read(rs.getString("meta_json"), Map.class));
  }
}
