package kr.co.axlink.standard.repository;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.standard.domain.ChangeRequestStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ChangeRequestRepository {

  private static final String COLS = """
      id, project_id, code, title, reason, impact_summary, status, requested_by_user_id,
      decided_by_user_id, requested_at, decided_at, applied_at, created_at, updated_at
      """;

  private static final Map<String, String> SORT = Map.of("updatedAt", "updated_at", "dueDate", "requested_at");

  private final JdbcClient jdbc;

  public ChangeRequestRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public List<StandardRows.ChangeRequestRow> search(UUID projectId, SortSpec sort, PageQuery page) {
    return jdbc.sql("select " + COLS + """
        from change_request where project_id = :projectId
        order by """ + sort.toOrderByClause() + " limit :limit offset :offset")
        .param("projectId", projectId).param("limit", page.limit()).param("offset", page.offset())
        .query(this::map).list();
  }

  public long countSearch(UUID projectId) {
    return jdbc.sql("select count(*) from change_request where project_id = :projectId")
        .param("projectId", projectId).query(Long.class).single();
  }

  public Optional<StandardRows.ChangeRequestRow> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from change_request where id = :id")
        .param("id", id).query(this::map).optional();
  }

  public int updateStatus(UUID id, ChangeRequestStatus next, UUID decidedByUserId, Instant now) {
    return jdbc.sql("""
        update change_request set status = :status, decided_by_user_id = :decidedBy,
               decided_at = :now, updated_at = :now
         where id = :id
        """)
        .param("status", next.name()).param("decidedBy", decidedByUserId)
        .param("now", RowReaders.utc(now)).param("id", id).update();
  }

  public int markApplied(UUID id, Instant now) {
    return jdbc.sql("""
        update change_request set status = 'APPLIED', applied_at = :now, updated_at = :now
         where id = :id
        """)
        .param("now", RowReaders.utc(now)).param("id", id).update();
  }

  public static SortSpec sort(List<String> raw) {
    return SortSpec.parse(raw, SORT, "updated_at desc");
  }

  private StandardRows.ChangeRequestRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.ChangeRequestRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        rs.getString("code"), rs.getString("title"), rs.getString("reason"), rs.getString("impact_summary"),
        ChangeRequestStatus.valueOf(rs.getString("status")),
        RowReaders.uuidNullable(rs, "requested_by_user_id"), RowReaders.uuidNullable(rs, "decided_by_user_id"),
        RowReaders.instant(rs, "requested_at"), RowReaders.instant(rs, "decided_at"),
        RowReaders.instant(rs, "applied_at"), RowReaders.instant(rs, "created_at"),
        RowReaders.instant(rs, "updated_at"));
  }
}
