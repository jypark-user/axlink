package kr.co.axlink.standard.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.domain.TraceLinkKind;
import kr.co.axlink.standard.domain.TraceLinkOrigin;
import kr.co.axlink.standard.domain.TraceLinkStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class TraceLinkRepository {

  private static final String COLS = """
      id, project_id, from_type, from_id, to_type, to_id, link_kind, origin, status,
      created_by_user_id, created_at, updated_at
      """;

  private static final Map<String, String> SORT = Map.of("createdAt", "created_at");

  private final JdbcClient jdbc;

  public TraceLinkRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public List<StandardRows.TraceLinkRow> search(UUID projectId, TraceEntityType fromType,
      TraceLinkKind linkKind, SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select ").append(COLS)
        .append(" from trace_link where project_id = :projectId");
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", projectId);
    if (fromType != null) {
      sql.append(" and from_type = :fromType");
      params.put("fromType", fromType.name());
    }
    if (linkKind != null) {
      sql.append(" and link_kind = :linkKind");
      params.put("linkKind", linkKind.name());
    }
    sql.append(" order by ").append(sort.toOrderByClause())
        .append(" limit :limit offset :offset");
    params.put("limit", page.limit());
    params.put("offset", page.offset());
    return jdbc.sql(sql.toString()).params(params).query(this::map).list();
  }

  public long countSearch(UUID projectId, TraceEntityType fromType, TraceLinkKind linkKind) {
    StringBuilder sql = new StringBuilder("select count(*) from trace_link where project_id = :projectId");
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", projectId);
    if (fromType != null) {
      sql.append(" and from_type = :fromType");
      params.put("fromType", fromType.name());
    }
    if (linkKind != null) {
      sql.append(" and link_kind = :linkKind");
      params.put("linkKind", linkKind.name());
    }
    return jdbc.sql(sql.toString()).params(params).query(Long.class).single();
  }

  public List<StandardRows.TraceLinkRow> findByFromOrTo(UUID projectId, TraceEntityType type, UUID entityId) {
    return jdbc.sql("select " + COLS + """
        from trace_link where project_id = :projectId
          and ((from_type = :type and from_id = :id) or (to_type = :type and to_id = :id))
        """)
        .param("projectId", projectId).param("type", type.name()).param("id", entityId)
        .query(this::map).list();
  }

  public boolean entityExists(UUID projectId, TraceEntityType type, UUID id) {
    String table = switch (type) {
      case REQUIREMENT -> "requirement";
      case ISSUE -> "issue";
      case WORK_PRODUCT -> "work_product";
      case RISK -> "risk";
      case CODE_CHANGE -> "code_change";
      case CHANGE_REQUEST -> "change_request";
      case CORRECTION_ACTION -> "correction_action";
    };
    return jdbc.sql("select 1 from " + table + " where id = :id and project_id = :pid")
        .param("id", id).param("pid", projectId).query(Integer.class).list().size() > 0;
  }

  public UUID insert(UUID projectId, TraceEntityType fromType, UUID fromId, TraceEntityType toType,
      UUID toId, TraceLinkKind kind, TraceLinkOrigin origin, UUID createdByUserId, Instant now) {
    return jdbc.sql("""
        insert into trace_link (project_id, from_type, from_id, to_type, to_id, link_kind, origin,
                               status, created_by_user_id, created_at, updated_at)
        values (:projectId, :fromType, :fromId, :toType, :toId, :kind, :origin, 'ACTIVE',
                :createdBy, :now, :now)
        on conflict (from_type, from_id, to_type, to_id, link_kind) do nothing
        returning id
        """)
        .param("projectId", projectId)
        .param("fromType", fromType.name())
        .param("fromId", fromId)
        .param("toType", toType.name())
        .param("toId", toId)
        .param("kind", kind.name())
        .param("origin", origin.name())
        .param("createdBy", createdByUserId)
        .param("now", RowReaders.utc(now))
        .query(UUID.class).optional().orElse(null);
  }

  public int delete(UUID id, UUID userId, Instant now) {
    return jdbc.sql("delete from trace_link where id = :id")
        .param("id", id).update();
  }

  public Optional<StandardRows.TraceLinkRow> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from trace_link where id = :id")
        .param("id", id).query(this::map).optional();
  }

  public List<StandardRows.TraceLinkRow> findByProject(UUID projectId) {
    return jdbc.sql("select " + COLS + " from trace_link where project_id = :projectId")
        .param("projectId", projectId).query(this::map).list();
  }

  public static SortSpec sort(List<String> raw) {
    return SortSpec.parse(raw, SORT, "created_at desc");
  }

  private StandardRows.TraceLinkRow map(ResultSet rs, int n) throws SQLException {
    return new StandardRows.TraceLinkRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        TraceEntityType.valueOf(rs.getString("from_type")), RowReaders.uuid(rs, "from_id"),
        TraceEntityType.valueOf(rs.getString("to_type")), RowReaders.uuid(rs, "to_id"),
        TraceLinkKind.valueOf(rs.getString("link_kind")),
        TraceLinkOrigin.valueOf(rs.getString("origin")),
        TraceLinkStatus.valueOf(rs.getString("status")),
        RowReaders.uuidNullable(rs, "created_by_user_id"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }
}
