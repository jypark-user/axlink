package kr.co.axlink.standard.repository;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.standard.domain.RiskLevel;
import kr.co.axlink.standard.domain.RiskStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class RiskRepository {

  private static final String COLS = """
      id, project_id, title, body, probability, impact, severity, mitigation, owner, status,
      identified_at, closed_at, tool_connection_id, external_id, external_url, source_kind,
      created_at, updated_at
      """;

  private static final Map<String, String> SORT = Map.of(
      "severity", "severity", "updatedAt", "updated_at");

  private final JdbcClient jdbc;

  public RiskRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public List<StandardRows.RiskRow> search(UUID projectId, RiskStatus status, RiskLevel severity,
      SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select ").append(COLS)
        .append(" from risk where project_id = :projectId");
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
    sql.append(" order by ").append(sort.toOrderByClause())
        .append(" limit :limit offset :offset");
    params.put("limit", page.limit());
    params.put("offset", page.offset());
    return jdbc.sql(sql.toString()).params(params).query(this::map).list();
  }

  public long countSearch(UUID projectId, RiskStatus status, RiskLevel severity) {
    StringBuilder sql = new StringBuilder("select count(*) from risk where project_id = :projectId");
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
    return jdbc.sql(sql.toString()).params(params).query(Long.class).single();
  }

  public Optional<StandardRows.UpsertOutcome> upsertFromTool(UUID projectId, UUID connectionId,
      String externalId, String externalUrl, Map<String, Object> f) {
    String sql = """
        insert into risk (id, project_id, tool_connection_id, external_id, external_url, source_kind,
                          title, body, probability, impact, severity, mitigation, owner, status,
                          identified_at, created_at, updated_at)
        values (gen_random_uuid(), :projectId, :connectionId, :externalId, :externalUrl, 'TOOL',
                :title, :body, :probability, :impact, :severity, :mitigation, :owner, :status,
                :identifiedAt, now(), now())
        on conflict (tool_connection_id, external_id)
          where tool_connection_id is not null and external_id is not null
        do update set
          title = excluded.title, body = excluded.body,
          probability = excluded.probability, impact = excluded.impact, severity = excluded.severity,
          mitigation = excluded.mitigation, owner = excluded.owner, status = excluded.status,
          external_url = excluded.external_url, updated_at = now()
        where risk.title is distinct from excluded.title
           or risk.severity is distinct from excluded.severity
           or risk.status is distinct from excluded.status
        returning id, (xmax = 0) as inserted, status
        """;
    return jdbc.sql(sql)
        .param("projectId", projectId)
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .param("externalUrl", externalUrl)
        .param("title", f.get("title"))
        .param("body", f.get("body"))
        .param("probability", f.get("probability"))
        .param("impact", f.get("impact"))
        .param("severity", f.get("severity"))
        .param("mitigation", f.get("mitigation"))
        .param("owner", f.get("owner"))
        .param("status", f.get("status"))
        .param("identifiedAt", f.get("identifiedAt"))
        .query((rs, n) -> new StandardRows.UpsertOutcome(
            RowReaders.uuid(rs, "id"), rs.getBoolean("inserted"), rs.getString("status")))
        .optional();
  }

  public static SortSpec sort(List<String> raw) {
    return SortSpec.parse(raw, SORT, "severity desc");
  }

  private StandardRows.RiskRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.RiskRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        rs.getString("title"), rs.getString("body"),
        RowReaders.en(rs, "probability", RiskLevel.class), RowReaders.en(rs, "impact", RiskLevel.class),
        RowReaders.en(rs, "severity", RiskLevel.class), rs.getString("mitigation"),
        rs.getString("owner"), RowReaders.en(rs, "status", RiskStatus.class),
        RowReaders.date(rs, "identified_at"), RowReaders.instant(rs, "closed_at"),
        RowReaders.uuidNullable(rs, "tool_connection_id"), rs.getString("external_id"),
        rs.getString("external_url"), rs.getString("source_kind"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }
}
