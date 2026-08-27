package kr.co.axlink.dashboard.repository;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.Dashboard;
import kr.co.axlink.dashboard.domain.DashboardStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class DashboardRepository {

  private final JdbcClient jdbcClient;

  public DashboardRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  /**
   * 내가 만든 대시보드 + 접근 가능한 사업의 기본 대시보드(진행 상황).
   * 기본 대시보드는 사업 단위로 하나뿐이므로 만든 사람만 보면 안 된다.
   */
  public List<Dashboard> list(UUID projectId, UUID ownerUserId, Set<UUID> allowedProjectIds) {
    if (projectId == null) {
      return jdbcClient.sql("""
          select id, project_id, owner_user_id, name, layout_json, is_default, status,
                 created_at, updated_at
            from dashboard
           where status = 'ACTIVE'
             and (owner_user_id = :ownerUserId
                  or (is_default and project_id = any(:allowedProjectIds)))
           order by is_default desc, updated_at desc
          """)
          .param("ownerUserId", ownerUserId)
          .param("allowedProjectIds", allowedProjectIds.toArray(new UUID[0]))
          .query(DashboardRepository::map).list();
    }
    return jdbcClient.sql("""
        select id, project_id, owner_user_id, name, layout_json, is_default, status,
               created_at, updated_at
          from dashboard
         where status = 'ACTIVE' and project_id = :projectId
           and (owner_user_id = :ownerUserId or is_default)
         order by is_default desc, updated_at desc
        """)
        .param("ownerUserId", ownerUserId)
        .param("projectId", projectId)
        .query(DashboardRepository::map).list();
  }

  public Optional<Dashboard> find(UUID id) {
    return jdbcClient.sql("""
        select id, project_id, owner_user_id, name, layout_json, is_default, status,
               created_at, updated_at
          from dashboard
         where id = :id and status = 'ACTIVE'
        """)
        .param("id", id)
        .query(DashboardRepository::map).optional();
  }

  public UUID create(UUID projectId, UUID ownerUserId, String name, String layoutJson) {
    return jdbcClient.sql("""
        insert into dashboard (project_id, owner_user_id, name, layout_json)
        values (:projectId, :ownerUserId, :name, cast(:layoutJson as jsonb))
        returning id
        """)
        .param("projectId", projectId)
        .param("ownerUserId", ownerUserId)
        .param("name", name)
        .param("layoutJson", layoutJson)
        .query(UUID.class).single();
  }

  public void updateName(UUID id, String name) {
    jdbcClient.sql("update dashboard set name = :name, updated_at = now() where id = :id")
        .param("id", id)
        .param("name", name)
        .update();
  }

  public void updateLayout(UUID id, String layoutJson) {
    jdbcClient.sql("update dashboard set layout_json = cast(:layoutJson as jsonb), updated_at = now() where id = :id")
        .param("id", id)
        .param("layoutJson", layoutJson)
        .update();
  }

  public void softDelete(UUID id) {
    jdbcClient.sql("update dashboard set status = 'DELETED', is_default = false, updated_at = now() where id = :id")
        .param("id", id)
        .update();
  }

  public void clearDefault(UUID projectId) {
    if (projectId == null) {
      return;
    }
    jdbcClient.sql("update dashboard set is_default = false where project_id = :projectId and is_default")
        .param("projectId", projectId)
        .update();
  }

  public void setDefault(UUID id) {
    jdbcClient.sql("update dashboard set is_default = true where id = :id")
        .param("id", id)
        .update();
  }

  public String projectName(UUID projectId) {
    if (projectId == null) {
      return null;
    }
    return jdbcClient.sql("select name from project where id = :id")
        .param("id", projectId)
        .query(String.class).optional().orElse(null);
  }

  private static Dashboard map(java.sql.ResultSet rs, int row) throws java.sql.SQLException {
    return new Dashboard(
        rs.getObject("id", UUID.class),
        rs.getObject("project_id", UUID.class),
        rs.getObject("owner_user_id", UUID.class),
        rs.getString("name"),
        rs.getString("layout_json"),
        rs.getBoolean("is_default"),
        DashboardStatus.parse(rs.getString("status")),
        rs.getTimestamp("created_at").toInstant(),
        rs.getTimestamp("updated_at").toInstant());
  }
}
