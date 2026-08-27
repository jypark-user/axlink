package kr.co.axlink.document.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.document.domain.DocumentUpload;
import kr.co.axlink.document.domain.DocumentUploadStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentUploadRepository {

  private static final String COLS = """
      id, project_id, uploaded_by_user_id, original_filename, stored_path, content_type, file_ext,
      size_bytes, file_hash, extracted_text, page_count, status, error, created_at, updated_at
      """;

  private final JdbcClient jdbc;

  public DocumentUploadRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public UUID insert(UUID projectId, UUID uploadedBy, String originalFilename, String storedPath,
      String contentType, String fileExt, long sizeBytes, String fileHash) {
    return jdbc.sql("""
        insert into document_upload (project_id, uploaded_by_user_id, original_filename, stored_path,
            content_type, file_ext, size_bytes, file_hash, status)
        values (:projectId, :uploadedBy, :originalFilename, :storedPath, :contentType, :fileExt,
            :sizeBytes, :fileHash, 'UPLOADED')
        returning id
        """)
        .param("projectId", projectId).param("uploadedBy", uploadedBy)
        .param("originalFilename", originalFilename).param("storedPath", storedPath)
        .param("contentType", contentType).param("fileExt", fileExt)
        .param("sizeBytes", sizeBytes).param("fileHash", fileHash)
        .query(UUID.class).single();
  }

  public Optional<DocumentUpload> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from document_upload where id = :id")
        .param("id", id).query(this::map).optional();
  }

  public List<DocumentUpload> search(UUID projectId, DocumentUploadStatus status, SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select ").append(COLS)
        .append(" from document_upload where project_id = :projectId");
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", projectId);
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    sql.append(" order by ").append(sort.toOrderByClause())
        .append(" limit :limit offset :offset");
    params.put("limit", page.limit());
    params.put("offset", page.offset());
    return jdbc.sql(sql.toString()).params(params).query(this::map).list();
  }

  public long countSearch(UUID projectId, DocumentUploadStatus status) {
    StringBuilder sql = new StringBuilder("select count(*) from document_upload where project_id = :projectId");
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", projectId);
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    return jdbc.sql(sql.toString()).params(params).query(Long.class).single();
  }

  public int updateExtracted(UUID id, String extractedText, Integer pageCount, DocumentUploadStatus status) {
    return jdbc.sql("""
        update document_upload set extracted_text = :text, page_count = :pages, status = :status,
               updated_at = now()
         where id = :id
        """)
        .param("text", extractedText).param("pages", pageCount)
        .param("status", status.name()).param("id", id).update();
  }

  public int updateStatus(UUID id, DocumentUploadStatus status, String error) {
    return jdbc.sql("update document_upload set status = :status, error = :error, updated_at = now() where id = :id")
        .param("status", status.name()).param("error", error).param("id", id).update();
  }

  public int delete(UUID id) {
    return jdbc.sql("delete from document_upload where id = :id").param("id", id).update();
  }

  public boolean existsByFileHash(UUID projectId, String fileHash) {
    return jdbc.sql("select 1 from document_upload where project_id = :pid and file_hash = :hash")
        .param("pid", projectId).param("hash", fileHash).query(Integer.class).list().size() > 0;
  }

  private DocumentUpload map(ResultSet rs, int n) throws SQLException {
    return new DocumentUpload(
        rs.getObject("id", UUID.class), rs.getObject("project_id", UUID.class),
        rs.getObject("uploaded_by_user_id", UUID.class), rs.getString("original_filename"),
        rs.getString("stored_path"), rs.getString("content_type"), rs.getString("file_ext"),
        rs.getLong("size_bytes"), rs.getString("file_hash"), rs.getString("extracted_text"),
        (Integer) rs.getObject("page_count"),
        DocumentUploadStatus.valueOf(rs.getString("status")), rs.getString("error"),
        readInst(rs, "created_at"), readInst(rs, "updated_at"));
  }

  private static Instant readInst(ResultSet rs, String col) throws SQLException {
    OffsetDateTime ts = rs.getObject(col, OffsetDateTime.class);
    return ts == null ? null : ts.toInstant();
  }
}
