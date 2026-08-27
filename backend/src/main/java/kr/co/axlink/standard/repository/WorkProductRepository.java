package kr.co.axlink.standard.repository;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.integration.port.WorkProductType;
import kr.co.axlink.standard.domain.PmActivity;
import kr.co.axlink.standard.domain.SiActivity;
import kr.co.axlink.standard.domain.WorkProductStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class WorkProductRepository {

  private static final String COLS = """
      id, project_id, type, version, title, status, applicable, is_current, pm_activity, si_activity,
      document_upload_id, file_uri, authored_at, due_date, submitted_at, approved_by_user_id, approved_at,
      reject_reason, tool_connection_id, external_id, external_url, source_kind, created_at, updated_at
      """;

  private final JdbcClient jdbc;

  public WorkProductRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 유형마다 수정일이 가장 최근인 행이 최신 버전이다 (PRD STD-001). */
  public List<StandardRows.WorkProductRow> checklist(UUID projectId) {
    return jdbc.sql("""
        select distinct on (type) """ + COLS + """
          from work_product where project_id = :projectId
         order by type, updated_at desc, created_at desc
        """)
        .param("projectId", projectId).query(this::map).list();
  }

  public Optional<StandardRows.WorkProductRow> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from work_product where id = :id")
        .param("id", id).query(this::map).optional();
  }

  public List<StandardRows.WorkProductRow> findVersions(UUID projectId, WorkProductType type) {
    return jdbc.sql("select " + COLS + " from work_product where project_id = :projectId and type = :type")
        .param("projectId", projectId).param("type", type.name())
        .query(this::map).list();
  }

  public Optional<StandardRows.WorkProductRow> findByTypeCurrent(UUID projectId, WorkProductType type) {
    return jdbc.sql("select " + COLS + """
        from work_product where project_id = :projectId and type = :type and is_current
        """)
        .param("projectId", projectId).param("type", type.name())
        .query(this::map).optional();
  }

  public UUID upsertNewVersion(UUID projectId, WorkProductType type, String version, String title,
      UUID documentUploadId, String fileUri, LocalDate authoredAt, PmActivity pm, SiActivity si,
      WorkProductStatus status) {
    jdbc.sql("""
        update work_product set is_current = false, updated_at = now()
         where project_id = :projectId and type = :type and is_current
        """)
        .param("projectId", projectId).param("type", type.name()).update();
    return jdbc.sql("""
        insert into work_product (project_id, type, version, title, status, applicable, is_current,
                                  pm_activity, si_activity, document_upload_id, file_uri, authored_at)
        values (:projectId, :type, :version, :title, :status, true, true,
                :pm, :si, :documentUploadId, :fileUri, :authoredAt)
        returning id
        """)
        .param("projectId", projectId)
        .param("type", type.name())
        .param("version", version)
        .param("title", title)
        .param("status", status.name())
        .param("pm", pm == null ? null : pm.name())
        .param("si", si == null ? null : si.name())
        .param("documentUploadId", documentUploadId)
        .param("fileUri", fileUri)
        .param("authoredAt", authoredAt)
        .query(UUID.class).single();
  }

  public Optional<StandardRows.UpsertOutcome> upsertFromTool(UUID projectId, UUID connectionId,
      String externalId, String externalUrl, WorkProductType type, Map<String, Object> f) {
    String sql = """
        insert into work_product (id, project_id, type, version, title, status, applicable, is_current,
                                  pm_activity, si_activity, tool_connection_id, external_id, external_url,
                                  source_kind, authored_at, created_at, updated_at)
        values (gen_random_uuid(), :projectId, :type, coalesce(:version, '0'), :title, :status, true, true,
                :pm, :si, :connectionId, :externalId, :externalUrl, 'TOOL',
                :authoredAt, now(), now())
        on conflict (tool_connection_id, external_id)
          where tool_connection_id is not null and external_id is not null
        do update set
          title = excluded.title, status = excluded.status,
          pm_activity = excluded.pm_activity, si_activity = excluded.si_activity,
          external_url = excluded.external_url, updated_at = now()
        where work_product.title is distinct from excluded.title
           or work_product.status is distinct from excluded.status
        returning id, (xmax = 0) as inserted, status
        """;
    return jdbc.sql(sql)
        .param("projectId", projectId)
        .param("type", type.name())
        .param("version", f.get("version"))
        .param("title", f.get("title"))
        .param("status", f.getOrDefault("status", "NONE"))
        .param("pm", f.get("pmActivity"))
        .param("si", f.get("siActivity"))
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .param("externalUrl", externalUrl)
        .param("authoredAt", f.get("authoredAt"))
        .query((rs, n) -> new StandardRows.UpsertOutcome(
            RowReaders.uuid(rs, "id"), rs.getBoolean("inserted"), rs.getString("status")))
        .optional();
  }

  public int backfillMissingChecklistRows(UUID projectId) {
    return jdbc.sql("""
        insert into work_product (project_id, type, applicable, is_current, pm_activity, si_activity)
        select t.project_id, t.type, true, true, t.pm_activity, t.si_activity
          from (values
            (:pid, 'STATEMENT_OF_WORK', 'PM_1', null),
            (:pid, 'PROJECT_PLAN', 'PM_1', null),
            (:pid, 'PROGRESS_STATUS_RECORD', 'PM_2', null),
            (:pid, 'MEETING_RECORD', 'PM_2', null),
            (:pid, 'CHANGE_REQUEST', 'PM_2', null),
            (:pid, 'CORRECTION_REGISTER', 'PM_3', null),
            (:pid, 'ACCEPTANCE_RECORD', 'PM_4', null),
            (:pid, 'PROJECT_REPOSITORY', 'PM_1', null),
            (:pid, 'REPOSITORY_BACKUP', 'PM_2', null),
            (:pid, 'VERIFICATION_RESULTS', 'PM_3', null),
            (:pid, 'VALIDATION_RESULTS', 'PM_4', null),
            (:pid, 'REQUIREMENTS_SPEC', null, 'SI_2'),
            (:pid, 'TRACEABILITY_RECORD', null, 'SI_2'),
            (:pid, 'SOFTWARE_DESIGN', null, 'SI_3'),
            (:pid, 'TEST_CASES_PROCEDURES', null, 'SI_3'),
            (:pid, 'SOFTWARE_COMPONENT', null, 'SI_4'),
            (:pid, 'SOFTWARE', null, 'SI_5'),
            (:pid, 'TEST_REPORT', null, 'SI_5'),
            (:pid, 'PRODUCT_OPERATION_GUIDE', null, 'SI_5'),
            (:pid, 'SOFTWARE_USER_DOC', null, 'SI_5'),
            (:pid, 'SOFTWARE_CONFIGURATION', null, 'SI_6'),
            (:pid, 'MAINTENANCE_DOC', null, 'SI_6')
          ) as t (project_id, type, pm_activity, si_activity)
         where not exists (
           select 1 from work_product w
            where w.project_id = t.project_id and w.type = t.type and w.is_current)
        """).param("pid", projectId).update();
  }

  public int countChunks(UUID workProductId) {
    return jdbc.sql("select count(*) from doc_chunk where source_type = 'WORK_PRODUCT' and source_id = :id")
        .param("id", workProductId).query(Integer.class).single();
  }

  private StandardRows.WorkProductRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.WorkProductRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        WorkProductType.valueOf(rs.getString("type")), rs.getString("version"), rs.getString("title"),
        WorkProductStatus.valueOf(rs.getString("status")), RowReaders.bool(rs, "applicable"),
        RowReaders.bool(rs, "is_current"), RowReaders.en(rs, "pm_activity", PmActivity.class),
        RowReaders.en(rs, "si_activity", SiActivity.class), RowReaders.uuidNullable(rs, "document_upload_id"),
        rs.getString("file_uri"), RowReaders.date(rs, "authored_at"), RowReaders.date(rs, "due_date"),
        RowReaders.instant(rs, "submitted_at"),
        RowReaders.uuidNullable(rs, "approved_by_user_id"), RowReaders.instant(rs, "approved_at"),
        rs.getString("reject_reason"), RowReaders.uuidNullable(rs, "tool_connection_id"),
        rs.getString("external_id"), rs.getString("external_url"), rs.getString("source_kind"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }
}
