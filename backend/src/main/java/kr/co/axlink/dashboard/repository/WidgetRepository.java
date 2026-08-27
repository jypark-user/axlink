package kr.co.axlink.dashboard.repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.Widget;
import kr.co.axlink.dashboard.domain.WidgetStatus;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class WidgetRepository {

  private final JdbcClient jdbcClient;

  public WidgetRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public List<Widget> listByDashboard(UUID dashboardId) {
    return jdbcClient.sql("""
        select id, dashboard_id, template, title, spec_json, status, created_by_user_id,
               created_at, updated_at
          from widget
         where dashboard_id = :dashboardId and status = 'ACTIVE'
         order by created_at
        """)
        .param("dashboardId", dashboardId)
        .query(WidgetRepository::map).list();
  }

  public int countByDashboard(UUID dashboardId) {
    return jdbcClient.sql("""
        select count(*) from widget
         where dashboard_id = :dashboardId and status = 'ACTIVE'
        """)
        .param("dashboardId", dashboardId)
        .query(Integer.class).single();
  }

  public Optional<Widget> find(UUID id) {
    return jdbcClient.sql("""
        select id, dashboard_id, template, title, spec_json, status, created_by_user_id,
               created_at, updated_at
          from widget
         where id = :id and status = 'ACTIVE'
        """)
        .param("id", id)
        .query(WidgetRepository::map).optional();
  }

  public UUID create(UUID dashboardId, WidgetTemplate template, String title, String specJson,
      UUID createdByUserId) {
    return jdbcClient.sql("""
        insert into widget (dashboard_id, template, title, spec_json, created_by_user_id)
        values (:dashboardId, :template, :title, cast(:specJson as jsonb), :createdByUserId)
        returning id
        """)
        .param("dashboardId", dashboardId)
        .param("template", template.name())
        .param("title", title)
        .param("specJson", specJson)
        .param("createdByUserId", createdByUserId)
        .query(UUID.class).single();
  }

  public void update(UUID id, WidgetTemplate template, String title, String specJson) {
    jdbcClient.sql("""
        update widget
           set template = :template, title = :title, spec_json = cast(:specJson as jsonb),
               updated_at = now()
         where id = :id
        """)
        .param("id", id)
        .param("template", template.name())
        .param("title", title)
        .param("specJson", specJson)
        .update();
  }

  public void softDelete(UUID id) {
    jdbcClient.sql("update widget set status = 'DELETED', updated_at = now() where id = :id")
        .param("id", id)
        .update();
  }

  public UUID dashboardIdOf(UUID widgetId) {
    return jdbcClient.sql("select dashboard_id from widget where id = :id")
        .param("id", widgetId)
        .query(UUID.class).optional().orElse(null);
  }

  public UUID ownerIdOfDashboard(UUID dashboardId) {
    return jdbcClient.sql("select owner_user_id from dashboard where id = :id")
        .param("id", dashboardId)
        .query(UUID.class).optional().orElse(null);
  }

  private static Widget map(java.sql.ResultSet rs, int row) throws java.sql.SQLException {
    return new Widget(
        rs.getObject("id", UUID.class),
        rs.getObject("dashboard_id", UUID.class),
        WidgetTemplate.parse(rs.getString("template")),
        rs.getString("title"),
        rs.getString("spec_json"),
        WidgetStatus.parse(rs.getString("status")),
        rs.getObject("created_by_user_id", UUID.class),
        rs.getTimestamp("created_at").toInstant(),
        rs.getTimestamp("updated_at").toInstant());
  }
}
