package kr.co.axlink.document.repository;

import com.fasterxml.jackson.databind.JsonNode;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.document.domain.StructuringDraft;
import kr.co.axlink.document.domain.StructuringDraftStatus;
import kr.co.axlink.integration.port.WorkProductType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class StructuringDraftRepository {

  private static final String COLS = """
      id, document_upload_id, model, draft_json, proposed_type, type_rejected, status,
      confirmed_by_user_id, confirmed_at, work_product_id, created_at, updated_at
      """;

  private final JdbcClient jdbc;
  private final JsonCodec json;

  public StructuringDraftRepository(JdbcClient jdbc, JsonCodec json) {
    this.jdbc = jdbc;
    this.json = json;
  }

  public void insert(UUID documentUploadId, String model, JsonNode draftJson, WorkProductType proposedType,
      boolean typeRejected) {
    jdbc.sql("""
        insert into structuring_draft (document_upload_id, model, draft_json, proposed_type, type_rejected, status)
        values (:documentUploadId, :model, :draftJson::jsonb, :proposedType, :typeRejected, 'PROPOSED')
        """)
        .param("documentUploadId", documentUploadId)
        .param("model", model)
        .param("draftJson", json.write(draftJson))
        .param("proposedType", proposedType == null ? null : proposedType.name())
        .param("typeRejected", typeRejected)
        .update();
  }

  public Optional<StructuringDraft> findByDocumentUploadId(UUID documentUploadId) {
    return jdbc.sql("select " + COLS + " from structuring_draft where document_upload_id = :id")
        .param("id", documentUploadId).query(this::map).optional();
  }

  public int updateStatus(UUID id, StructuringDraftStatus status, UUID confirmedByUserId, UUID workProductId) {
    return jdbc.sql("""
        update structuring_draft set status = :status, confirmed_by_user_id = :confirmedBy,
               confirmed_at = now(), work_product_id = :workProductId, updated_at = now()
         where id = :id
        """)
        .param("status", status.name()).param("confirmedBy", confirmedByUserId)
        .param("workProductId", workProductId).param("id", id).update();
  }

  private StructuringDraft map(ResultSet rs, int n) throws SQLException {
    return new StructuringDraft(
        rs.getObject("id", UUID.class), rs.getObject("document_upload_id", UUID.class),
        rs.getString("model"), json.tree(rs.getString("draft_json")),
        readType(rs.getString("proposed_type")), rs.getBoolean("type_rejected"),
        StructuringDraftStatus.valueOf(rs.getString("status")),
        rs.getObject("confirmed_by_user_id", UUID.class), readInst(rs, "confirmed_at"),
        rs.getObject("work_product_id", UUID.class), readInst(rs, "created_at"), readInst(rs, "updated_at"));
  }

  private static WorkProductType readType(String v) {
    if (v == null) {
      return null;
    }
    try { return WorkProductType.valueOf(v); }
    catch (Exception e) { return null; }
  }

  private static Instant readInst(ResultSet rs, String col) throws SQLException {
    OffsetDateTime ts = rs.getObject(col, OffsetDateTime.class);
    return ts == null ? null : ts.toInstant();
  }
}
