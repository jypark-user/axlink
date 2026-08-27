package kr.co.axlink.standard.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.standard.domain.AcceptanceStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class GovernanceRepository {

  private static final String PROGRESS_COLS = """
      id, project_id, period_start, period_end, planned_pct, actual_pct, summary,
      tool_connection_id, external_id, external_url, source_kind, created_at, updated_at
      """;

  private static final String ACCEPTANCE_COLS = """
      id, project_id, accepted_by_user_id, accepted_at, conditions, work_product_id, status,
      voided_at, created_at, updated_at
      """;

  private static final Map<String, String> PROGRESS_SORT = Map.of("period", "period_end");

  private final JdbcClient jdbc;

  public GovernanceRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public List<StandardRows.ProgressRecordRow> searchProgress(UUID projectId, SortSpec sort, PageQuery page) {
    return jdbc.sql("select " + PROGRESS_COLS + """
        from progress_record where project_id = :projectId
        order by """ + sort.toOrderByClause() + " limit :limit offset :offset")
        .param("projectId", projectId).param("limit", page.limit()).param("offset", page.offset())
        .query(this::mapProgress).list();
  }

  public long countProgress(UUID projectId) {
    return jdbc.sql("select count(*) from progress_record where project_id = :projectId")
        .param("projectId", projectId).query(Long.class).single();
  }

  public Optional<StandardRows.UpsertOutcome> upsertProgressFromTool(UUID projectId, UUID connectionId,
      String externalId, String externalUrl, LocalDate periodStart, LocalDate periodEnd,
      double plannedPct, double actualPct, String summary) {
    String sql = """
        insert into progress_record (id, project_id, period_start, period_end, planned_pct, actual_pct,
                                     summary, tool_connection_id, external_id, external_url, source_kind)
        values (gen_random_uuid(), :projectId, :ps, :pe, :planned, :actual, :summary,
                :cid, :externalId, :externalUrl, 'TOOL')
        on conflict (tool_connection_id, external_id)
          where tool_connection_id is not null and external_id is not null
        do update set
          planned_pct = excluded.planned_pct, actual_pct = excluded.actual_pct,
          summary = excluded.summary, external_url = excluded.external_url, updated_at = now()
        where progress_record.actual_pct is distinct from excluded.actual_pct
           or progress_record.planned_pct is distinct from excluded.planned_pct
        returning id, (xmax = 0) as inserted, null as status
        """;
    return jdbc.sql(sql)
        .param("projectId", projectId).param("ps", periodStart).param("pe", periodEnd)
        .param("planned", plannedPct).param("actual", actualPct).param("summary", summary)
        .param("cid", connectionId).param("externalId", externalId).param("externalUrl", externalUrl)
        .query((rs, n) -> new StandardRows.UpsertOutcome(
            RowReaders.uuid(rs, "id"), rs.getBoolean("inserted"), rs.getString("status")))
        .optional();
  }

  public Optional<StandardRows.AcceptanceRow> findIssued(UUID projectId) {
    return jdbc.sql("select " + ACCEPTANCE_COLS + """
        from acceptance_record where project_id = :projectId and status = 'ISSUED'
        """)
        .param("projectId", projectId).query(this::mapAcceptance).optional();
  }

  public UUID insertAcceptance(UUID projectId, UUID acceptedByUserId, Instant acceptedAt,
      String conditions, UUID workProductId) {
    return jdbc.sql("""
        insert into acceptance_record (project_id, accepted_by_user_id, accepted_at, conditions,
                                        work_product_id, status)
        values (:projectId, :acceptedBy, :acceptedAt, :conditions, :workProductId, 'ISSUED')
        returning id
        """)
        .param("projectId", projectId).param("acceptedBy", acceptedByUserId)
        .param("acceptedAt", RowReaders.utc(acceptedAt)).param("conditions", conditions)
        .param("workProductId", workProductId).query(UUID.class).single();
  }

  public Optional<StandardRows.AcceptanceRow> findAcceptanceById(UUID id) {
    return jdbc.sql("select " + ACCEPTANCE_COLS + " from acceptance_record where id = :id")
        .param("id", id).query(this::mapAcceptance).optional();
  }

  public static SortSpec progressSort(List<String> raw) {
    return SortSpec.parse(raw, PROGRESS_SORT, "period_end desc");
  }

  private StandardRows.ProgressRecordRow mapProgress(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.ProgressRecordRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        RowReaders.date(rs, "period_start"), RowReaders.date(rs, "period_end"),
        rs.getDouble("planned_pct"), rs.getDouble("actual_pct"), rs.getString("summary"),
        RowReaders.uuidNullable(rs, "tool_connection_id"), rs.getString("external_id"),
        rs.getString("external_url"), rs.getString("source_kind"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }

  private StandardRows.AcceptanceRow mapAcceptance(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.AcceptanceRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        RowReaders.uuid(rs, "accepted_by_user_id"), RowReaders.instant(rs, "accepted_at"),
        rs.getString("conditions"), RowReaders.uuidNullable(rs, "work_product_id"),
        AcceptanceStatus.valueOf(rs.getString("status")), RowReaders.instant(rs, "voided_at"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }
}
