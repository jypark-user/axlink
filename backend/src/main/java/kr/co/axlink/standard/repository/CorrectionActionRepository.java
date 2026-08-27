package kr.co.axlink.standard.repository;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.standard.domain.CorrectionStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class CorrectionActionRepository {

  private static final String COLS = """
      id, project_id, code, finding, action, owner, due_date, status, source_work_product_id,
      done_at, tool_connection_id, external_id, external_url, source_kind, created_at, updated_at
      """;

  private static final Map<String, String> SORT = Map.of("updatedAt", "updated_at", "dueDate", "due_date");

  private final JdbcClient jdbc;

  public CorrectionActionRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public List<StandardRows.CorrectionActionRow> search(UUID projectId, CorrectionStatus status,
      SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select ").append(COLS)
        .append(" from correction_action where project_id = :projectId");
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

  public long countSearch(UUID projectId, CorrectionStatus status) {
    StringBuilder sql = new StringBuilder("select count(*) from correction_action where project_id = :projectId");
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", projectId);
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    return jdbc.sql(sql.toString()).params(params).query(Long.class).single();
  }

  public Optional<StandardRows.CorrectionActionRow> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from correction_action where id = :id")
        .param("id", id).query(this::map).optional();
  }

  /** 도구에서 수집한 시정조치. 식별은 (연동, 외부 id) 로 한다. */
  public Optional<StandardRows.UpsertOutcome> upsertFromTool(UUID projectId, UUID connectionId,
      String externalId, String externalUrl, Map<String, Object> f) {
    return jdbc.sql("""
        insert into correction_action (project_id, code, finding, action, owner, due_date, status,
                                       tool_connection_id, external_id, external_url, source_kind,
                                       created_at, updated_at)
        values (:projectId, :code, :finding, :action, :owner, cast(:dueDate as date), :status,
                :connectionId, :externalId, :externalUrl, 'TOOL', now(), now())
        on conflict (tool_connection_id, external_id)
          where tool_connection_id is not null and external_id is not null
        do update set
          finding = excluded.finding, action = excluded.action, owner = excluded.owner,
          due_date = excluded.due_date, status = excluded.status,
          external_url = excluded.external_url, updated_at = now()
        where correction_action.finding is distinct from excluded.finding
           or correction_action.action is distinct from excluded.action
           or correction_action.owner is distinct from excluded.owner
           or correction_action.due_date is distinct from excluded.due_date
           or correction_action.status is distinct from excluded.status
        returning id, (xmax = 0) as inserted, status
        """)
        .param("projectId", projectId)
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .param("externalUrl", externalUrl)
        .param("code", f.get("code"))
        .param("finding", f.get("finding"))
        .param("action", f.get("action"))
        .param("owner", f.get("owner"))
        .param("dueDate", f.get("dueDate"))
        .param("status", f.getOrDefault("status", CorrectionStatus.OPEN.name()))
        .query((rs, n) -> new StandardRows.UpsertOutcome(
            RowReaders.uuid(rs, "id"), rs.getBoolean("inserted"), rs.getString("status")))
        .optional();
  }

  public int updateStatus(UUID id, CorrectionStatus next, Instant now) {
    String doneAt = next == CorrectionStatus.DONE ? ", done_at = :now" : "";
    return jdbc.sql("update correction_action set status = :status" + doneAt
        + ", updated_at = :now where id = :id")
        .param("status", next.name()).param("now", RowReaders.utc(now)).param("id", id).update();
  }

  public int sweepOverdue() {
    return jdbc.sql("""
        update correction_action set status = 'OVERDUE', updated_at = now()
         where status = 'OPEN' and due_date < current_date
        """).update();
  }

  public static SortSpec sort(List<String> raw) {
    return SortSpec.parse(raw, SORT, "due_date asc");
  }

  private StandardRows.CorrectionActionRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.CorrectionActionRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        rs.getString("code"), rs.getString("finding"), rs.getString("action"), rs.getString("owner"),
        RowReaders.date(rs, "due_date"), CorrectionStatus.valueOf(rs.getString("status")),
        RowReaders.uuidNullable(rs, "source_work_product_id"), RowReaders.instant(rs, "done_at"),
        RowReaders.uuidNullable(rs, "tool_connection_id"), rs.getString("external_id"),
        rs.getString("external_url"), rs.getString("source_kind"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }
}
