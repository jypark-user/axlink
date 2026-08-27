package kr.co.axlink.standard.repository;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.standard.domain.CodeChangeKind;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class CodeChangeRepository {

  private static final String COLS = """
      id, project_id, kind, title, ref_name, state, author, occurred_at, work_product_id,
      tool_connection_id, external_id, external_url, source_kind, created_at, updated_at
      """;

  private final JdbcClient jdbc;

  public CodeChangeRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public Optional<StandardRows.CodeChangeRow> findById(UUID id) {
    return jdbc.sql("select " + COLS + " from code_change where id = :id")
        .param("id", id).query(this::map).optional();
  }

  public Optional<StandardRows.CodeChangeRow> findBySource(UUID connectionId, String externalId) {
    return jdbc.sql("select " + COLS + """
        from code_change where tool_connection_id = :cid and external_id = :eid
        """)
        .param("cid", connectionId).param("eid", externalId).query(this::map).optional();
  }

  public Optional<StandardRows.UpsertOutcome> upsertFromTool(UUID projectId, UUID connectionId,
      String externalId, String externalUrl, CodeChangeKind kind, Map<String, Object> f, Instant occurredAt) {
    String sql = """
        insert into code_change (id, project_id, kind, title, ref_name, state, author, occurred_at,
                                 work_product_id, tool_connection_id, external_id, external_url,
                                 source_kind, created_at, updated_at)
        values (gen_random_uuid(), :projectId, :kind, :title, :refName, :state, :author, :occurredAt,
                :workProductId, :connectionId, :externalId, :externalUrl, 'TOOL', now(), now())
        on conflict (tool_connection_id, external_id)
          where tool_connection_id is not null and external_id is not null
        do update set
          title = excluded.title, state = excluded.state, author = excluded.author,
          occurred_at = excluded.occurred_at, external_url = excluded.external_url, updated_at = now()
        where code_change.title is distinct from excluded.title
           or code_change.state is distinct from excluded.state
        returning id, (xmax = 0) as inserted, state
        """;
    return jdbc.sql(sql)
        .param("projectId", projectId)
        .param("kind", kind.name())
        .param("title", f.get("title"))
        .param("refName", f.get("refName"))
        .param("state", f.get("state"))
        .param("author", f.get("author"))
        .param("occurredAt", RowReaders.utc(occurredAt))
        .param("workProductId", f.get("workProductId"))
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .param("externalUrl", externalUrl)
        .query((rs, n) -> new StandardRows.UpsertOutcome(
            RowReaders.uuid(rs, "id"), rs.getBoolean("inserted"), rs.getString("state")))
        .optional();
  }

  private StandardRows.CodeChangeRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.CodeChangeRow(
        RowReaders.uuid(rs, "id"), RowReaders.uuid(rs, "project_id"),
        CodeChangeKind.valueOf(rs.getString("kind")), rs.getString("title"), rs.getString("ref_name"),
        kr.co.axlink.standard.domain.CodeChangeState.valueOf(rs.getString("state")),
        rs.getString("author"), RowReaders.instant(rs, "occurred_at"),
        RowReaders.uuidNullable(rs, "work_product_id"), RowReaders.uuidNullable(rs, "tool_connection_id"),
        rs.getString("external_id"), rs.getString("external_url"), rs.getString("source_kind"),
        RowReaders.instant(rs, "created_at"), RowReaders.instant(rs, "updated_at"));
  }
}
