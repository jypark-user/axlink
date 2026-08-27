package kr.co.axlink.standard.repository;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.standard.domain.IssueSeverity;
import kr.co.axlink.standard.domain.IssueStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class IssueRepository {

  private static final String COLS = """
      id, project_id, issue_key, title, body, status, severity, assignee,
      source_created_at, source_updated_at, resolved_at,
      tool_connection_id, external_id, external_url, source_kind, created_at, updated_at
      """;

  private static final Map<String, String> SORT = Map.of(
      "updatedAt", "updated_at", "severity", "severity", "resolvedAt", "resolved_at");

  private final JdbcClient jdbc;

  public IssueRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public List<StandardRows.IssueRow> search(UUID projectId, IssueStatus status, IssueSeverity severity,
      String assignee, String q, SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select ").append(COLS)
        .append(" from issue where project_id = :projectId");
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", projectId);
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (severity != null) {
      sql.append(" and severity = :severity");
      params.put("severity", severity.name());
    }
    if (assignee != null && !assignee.isBlank()) {
      sql.append(" and assignee = :assignee");
      params.put("assignee", assignee);
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

  public long countSearch(UUID projectId, IssueStatus status, IssueSeverity severity, String assignee, String q) {
    StringBuilder sql = new StringBuilder("select count(*) from issue where project_id = :projectId");
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", projectId);
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (severity != null) {
      sql.append(" and severity = :severity");
      params.put("severity", severity.name());
    }
    if (assignee != null && !assignee.isBlank()) {
      sql.append(" and assignee = :assignee");
      params.put("assignee", assignee);
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and title ilike :q");
      params.put("q", "%" + q + "%");
    }
    return jdbc.sql(sql.toString()).params(params).query(Long.class).single();
  }

  public Optional<StandardRows.IssueRow> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from issue where id = :id")
        .param("id", id).query(this::map).optional();
  }

  public Optional<StandardRows.IssueRow> findBySource(UUID connectionId, String externalId) {
    return jdbc.sql("select " + COLS + """
        from issue where tool_connection_id = :cid and external_id = :eid
        """)
        .param("cid", connectionId).param("eid", externalId).query(this::map).optional();
  }

  public int updateStatus(UUID id, IssueStatus next, Instant resolvedAt, Instant now) {
    return jdbc.sql("""
        update issue set status = :status, resolved_at = :resolvedAt, updated_at = :now
         where id = :id
        """)
        .param("status", next.name())
        .param("resolvedAt", RowReaders.utc(resolvedAt))
        .param("now", RowReaders.utc(now))
        .param("id", id).update();
  }

  public Optional<StandardRows.UpsertOutcome> upsertFromTool(UUID projectId, UUID connectionId,
      String externalId, String externalUrl, Map<String, Object> f, Instant createdAt, Instant updatedAt) {
    String sql = """
        insert into issue (id, project_id, tool_connection_id, external_id, external_url, source_kind,
                           issue_key, title, body, status, severity, assignee,
                           source_created_at, source_updated_at, resolved_at, created_at, updated_at)
        values (gen_random_uuid(), :projectId, :connectionId, :externalId, :externalUrl, 'TOOL',
                :issueKey, :title, :body, :status, :severity, :assignee,
                :sourceCreatedAt, :sourceUpdatedAt, :resolvedAt, now(), now())
        on conflict (tool_connection_id, external_id)
          where tool_connection_id is not null and external_id is not null
        do update set
          title = excluded.title, body = excluded.body, status = excluded.status,
          severity = excluded.severity, assignee = excluded.assignee,
          external_url = excluded.external_url,
          source_updated_at = excluded.source_updated_at, resolved_at = excluded.resolved_at,
          updated_at = now()
        where issue.title is distinct from excluded.title
           or issue.status is distinct from excluded.status
           or issue.severity is distinct from excluded.severity
           or issue.assignee is distinct from excluded.assignee
           or issue.resolved_at is distinct from excluded.resolved_at
        returning id, (xmax = 0) as inserted, status
        """;
    return jdbc.sql(sql)
        .param("projectId", projectId)
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .param("externalUrl", externalUrl)
        .param("issueKey", f.get("issueKey"))
        .param("title", f.get("title"))
        .param("body", f.get("body"))
        .param("status", f.get("status"))
        .param("severity", f.get("severity"))
        .param("assignee", f.get("assignee"))
        .param("sourceCreatedAt", RowReaders.utc(createdAt))
        .param("sourceUpdatedAt", RowReaders.utc(updatedAt))
        .param("resolvedAt", RowReaders.utc((Instant) f.get("resolvedAt")))
        .query((rs, n) -> new StandardRows.UpsertOutcome(
            RowReaders.uuid(rs, "id"), rs.getBoolean("inserted"), rs.getString("status")))
        .optional();
  }

  public static SortSpec sort(List<String> raw) {
    return SortSpec.parse(raw, SORT, "updated_at desc");
  }

  private StandardRows.IssueRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.IssueRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        rs.getString("issue_key"), rs.getString("title"), rs.getString("body"),
        RowReaders.en(rs, "status", IssueStatus.class), RowReaders.en(rs, "severity", IssueSeverity.class),
        rs.getString("assignee"), RowReaders.instant(rs, "source_created_at"),
        RowReaders.instant(rs, "source_updated_at"), RowReaders.instant(rs, "resolved_at"),
        RowReaders.uuidNullable(rs, "tool_connection_id"), rs.getString("external_id"),
        rs.getString("external_url"), rs.getString("source_kind"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }
}
