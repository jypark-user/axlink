package kr.co.axlink.standard.repository;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.standard.domain.RequirementPriority;
import kr.co.axlink.standard.domain.RequirementStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class RequirementRepository {

  private static final String COLS = """
      id, project_id, code, title, body, priority, status, work_product_id, document_upload_id,
      assignee, tool_connection_id, external_id, external_url, source_kind,
      source_created_at, source_updated_at, created_at, updated_at
      """;

  private static final Map<String, String> SORT = Map.of(
      "code", "code", "updatedAt", "updated_at", "priority", "priority");

  private final JdbcClient jdbc;

  public RequirementRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public List<StandardRows.RequirementRow> search(UUID projectId, RequirementStatus status,
      RequirementPriority priority, String q, SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select ").append(COLS)
        .append(" from requirement where project_id = :projectId");
    Map<String, Object> params = new java.util.LinkedHashMap<>();
    params.put("projectId", projectId);
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (priority != null) {
      sql.append(" and priority = :priority");
      params.put("priority", priority.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and title ilike :q");
      params.put("q", "%" + q + "%");
    }
    sql.append(" order by ").append(sort.toOrderByClause())
        .append(" limit :limit offset :offset");
    params.put("limit", page.limit());
    params.put("offset", page.offset());
    return jdbc.sql(sql.toString()).params(params).query(this::map).list();
  }

  public long countSearch(UUID projectId, RequirementStatus status, RequirementPriority priority, String q) {
    StringBuilder sql = new StringBuilder("select count(*) from requirement where project_id = :projectId");
    Map<String, Object> params = new java.util.LinkedHashMap<>();
    params.put("projectId", projectId);
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (priority != null) {
      sql.append(" and priority = :priority");
      params.put("priority", priority.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and title ilike :q");
      params.put("q", "%" + q + "%");
    }
    return jdbc.sql(sql.toString()).params(params).query(Long.class).single();
  }

  public Optional<StandardRows.RequirementRow> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from requirement where id = :id")
        .param("id", id).query(this::map).optional();
  }

  public int updateStatus(UUID id, RequirementStatus next, Instant now) {
    return jdbc.sql("update requirement set status = :status, updated_at = :now where id = :id")
        .param("status", next.name()).param("now", utc(now)).param("id", id).update();
  }

  public Optional<StandardRows.RequirementRow> findBySource(UUID connectionId, String externalId) {
    return jdbc.sql("select " + COLS + """
        from requirement where tool_connection_id = :cid and external_id = :eid
        """)
        .param("cid", connectionId).param("eid", externalId).query(this::map).optional();
  }

  public Optional<StandardRows.UpsertOutcome> upsertFromTool(UUID projectId, UUID connectionId,
      String externalId, String externalUrl, Map<String, Object> f, Instant createdAt, Instant updatedAt) {
    String sql = """
        insert into requirement (id, project_id, tool_connection_id, external_id, external_url, source_kind,
                                 code, title, body, priority, status, assignee,
                                 source_created_at, source_updated_at, created_at, updated_at)
        values (gen_random_uuid(), :projectId, :connectionId, :externalId, :externalUrl, 'TOOL',
                :code, :title, :body, :priority, :status, :assignee,
                :sourceCreatedAt, :sourceUpdatedAt, now(), now())
        on conflict (tool_connection_id, external_id)
          where tool_connection_id is not null and external_id is not null
        do update set
          title = excluded.title, body = excluded.body, status = excluded.status,
          priority = excluded.priority, assignee = excluded.assignee,
          external_url = excluded.external_url,
          source_updated_at = excluded.source_updated_at, updated_at = now()
        where requirement.title is distinct from excluded.title
           or requirement.status is distinct from excluded.status
           or requirement.priority is distinct from excluded.priority
        returning id, (xmax = 0) as inserted, status
        """;
    return jdbc.sql(sql)
        .param("projectId", projectId)
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .param("externalUrl", externalUrl)
        .param("code", f.get("code"))
        .param("title", f.get("title"))
        .param("body", f.get("body"))
        .param("priority", f.get("priority"))
        .param("status", f.get("status"))
        .param("assignee", f.get("assignee"))
        .param("sourceCreatedAt", RowReaders.utc(createdAt))
        .param("sourceUpdatedAt", RowReaders.utc(updatedAt))
        .query((rs, n) -> new StandardRows.UpsertOutcome(
            RowReaders.uuid(rs, "id"), rs.getBoolean("inserted"), rs.getString("status")))
        .optional();
  }

  public UUID insertFromDocument(UUID projectId, UUID workProductId, UUID documentUploadId,
      String code, String title, String body, RequirementPriority priority, RequirementStatus status) {
    return jdbc.sql("""
        insert into requirement (project_id, work_product_id, document_upload_id, source_kind,
                                 code, title, body, priority, status)
        values (:projectId, :workProductId, :documentUploadId, 'DOCUMENT',
                :code, :title, :body, :priority, :status)
        returning id
        """)
        .param("projectId", projectId).param("workProductId", workProductId)
        .param("documentUploadId", documentUploadId).param("code", code)
        .param("title", title).param("body", body)
        .param("priority", priority.name()).param("status", status.name())
        .query(UUID.class).single();
  }

  public static SortSpec sort(List<String> raw) {
    return SortSpec.parse(raw, SORT, "updated_at desc");
  }

  private StandardRows.RequirementRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.RequirementRow(
        rs.getObject("id", UUID.class), rs.getObject("project_id", UUID.class),
        rs.getString("code"), rs.getString("title"), rs.getString("body"),
        readPriority(rs.getString("priority")), readStatus(rs.getString("status")),
        rs.getObject("work_product_id", UUID.class), rs.getObject("document_upload_id", UUID.class),
        rs.getString("assignee"), rs.getObject("tool_connection_id", UUID.class),
        rs.getString("external_id"), rs.getString("external_url"), rs.getString("source_kind"),
        readInstant(rs, "source_created_at"), readInstant(rs, "source_updated_at"),
        readInstant(rs, "created_at"), readInstant(rs, "updated_at"));
  }

  private static OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(ZoneOffset.UTC);
  }

  private static Instant readInstant(java.sql.ResultSet rs, String col) throws java.sql.SQLException {
    var ts = rs.getObject(col, OffsetDateTime.class);
    return ts == null ? null : ts.toInstant();
  }

  private static RequirementPriority readPriority(String v) {
    return v == null ? null : RequirementPriority.valueOf(v);
  }

  private static RequirementStatus readStatus(String v) {
    return v == null ? null : RequirementStatus.valueOf(v);
  }
}
