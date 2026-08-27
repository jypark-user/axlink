package kr.co.axlink.standard.history;

import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.standard.domain.HistoryEntityType;
import kr.co.axlink.standard.repository.StandardRows;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class EntityHistoryRepository {

  private static final String COLS = """
      id, entity_type, entity_id, project_id, field, from_value, to_value, changed_at, actor, created_at
      """;

  private final JdbcClient jdbc;

  public EntityHistoryRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public void insert(HistoryEntityType type, UUID entityId, UUID projectId, String field,
      String from, String to, String actor) {
    jdbc.sql("""
        insert into entity_history (entity_type, entity_id, project_id, field, from_value, to_value,
                                     changed_at, actor)
        values (:type, :entityId, :projectId, :field, :from, :to, now(), :actor)
        """)
        .param("type", type.name()).param("entityId", entityId).param("projectId", projectId)
        .param("field", field).param("from", from).param("to", to).param("actor", actor).update();
  }

  public List<StandardRows.EntityHistoryRow> search(HistoryEntityType type, UUID entityId,
      Collection<UUID> projectIds, PageQuery page) {
    return jdbc.sql("select " + COLS + """
        from entity_history
         where entity_type = :type and entity_id = :entityId
         order by changed_at desc
         limit :limit offset :offset
        """)
        .param("type", type.name()).param("entityId", entityId)
        .param("limit", page.limit()).param("offset", page.offset())
        .query(this::map).list();
  }

  public long count(HistoryEntityType type, UUID entityId) {
    return jdbc.sql("select count(*) from entity_history where entity_type = :type and entity_id = :entityId")
        .param("type", type.name()).param("entityId", entityId).query(Long.class).single();
  }

  private StandardRows.EntityHistoryRow map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
    return new StandardRows.EntityHistoryRow(
        rs.getObject("id", UUID.class), HistoryEntityType.valueOf(rs.getString("entity_type")),
        rs.getObject("entity_id", UUID.class), rs.getObject("project_id", UUID.class),
        rs.getString("field"), rs.getString("from_value"), rs.getString("to_value"),
        readInstant(rs, "changed_at"), rs.getString("actor"),
        readInstant(rs, "created_at"));
  }

  private static java.time.Instant readInstant(java.sql.ResultSet rs, String col) throws java.sql.SQLException {
    OffsetDateTime ts = rs.getObject(col, OffsetDateTime.class);
    return ts == null ? null : ts.toInstant();
  }
}
