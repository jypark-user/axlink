package kr.co.axlink.project.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.project.domain.AssignmentStatus;
import kr.co.axlink.project.domain.ProjectAssignment;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ProjectAssignmentRepository {

  private static final String COLUMNS =
      "id, project_id, contractor_org_id, user_id, status, assigned_by_user_id, revoked_at, created_at, updated_at";

  private final JdbcClient jdbcClient;

  public ProjectAssignmentRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(ProjectAssignment a) {
    return jdbcClient.sql("""
        insert into project_assignment (project_id, contractor_org_id, user_id, status, assigned_by_user_id)
        values (:projectId, :contractorOrgId, :userId, :status, :assignedByUserId)
        returning id
        """)
        .param("projectId", a.projectId())
        .param("contractorOrgId", a.contractorOrgId())
        .param("userId", a.userId())
        .param("status", a.status() == null ? AssignmentStatus.ACTIVE.name() : a.status().name())
        .param("assignedByUserId", a.assignedByUserId())
        .query(UUID.class)
        .single();
  }

  public Set<UUID> findProjectIdsByUserIdAndStatus(UUID userId, AssignmentStatus status) {
    return new LinkedHashSet<>(jdbcClient.sql("""
        select project_id from project_assignment
         where user_id = :userId and status = :status
        """)
        .param("userId", userId)
        .param("status", status.name())
        .query(UUID.class)
        .list());
  }

  public Optional<ProjectAssignment> findActive(UUID userId, UUID projectId) {
    return jdbcClient.sql("select " + COLUMNS + " from project_assignment "
            + "where user_id = :userId and project_id = :projectId and status = 'ACTIVE'")
        .param("userId", userId)
        .param("projectId", projectId)
        .query(this::map)
        .optional();
  }

  public Optional<ProjectAssignment> findById(UUID id) {
    return jdbcClient.sql("select " + COLUMNS + " from project_assignment where id = :id")
        .param("id", id)
        .query(this::map)
        .optional();
  }

  public List<ProjectAssignment> findByProjectId(UUID projectId) {
    return jdbcClient.sql("select " + COLUMNS + " from project_assignment where project_id = :projectId order by created_at")
        .param("projectId", projectId)
        .query(this::map)
        .list();
  }

  public int revoke(UUID id, Instant at) {
    return jdbcClient.sql("""
        update project_assignment set status = 'REVOKED', revoked_at = :at, updated_at = now()
         where id = :id and status = 'ACTIVE'
        """)
        .param("id", id)
        .param("at", utc(at))
        .update();
  }

  public boolean existsActive(UUID projectId, UUID userId) {
    return jdbcClient.sql("""
        select 1 from project_assignment
         where project_id = :projectId and user_id = :userId and status = 'ACTIVE'
        """)
        .param("projectId", projectId)
        .param("userId", userId)
        .query(Integer.class)
        .optional()
        .isPresent();
  }

  private ProjectAssignment map(ResultSet rs, int rowNum) throws SQLException {
    return new ProjectAssignment(
        rs.getObject("id", UUID.class),
        rs.getObject("project_id", UUID.class),
        rs.getObject("contractor_org_id", UUID.class),
        rs.getObject("user_id", UUID.class),
        AssignmentStatus.valueOf(rs.getString("status")),
        rs.getObject("assigned_by_user_id", UUID.class),
        toInstant(rs, "revoked_at"),
        toInstant(rs, "created_at"),
        toInstant(rs, "updated_at"));
  }

  private static Instant toInstant(ResultSet rs, String column) throws SQLException {
    OffsetDateTime odt = rs.getObject(column, OffsetDateTime.class);
    return odt == null ? null : odt.toInstant();
  }

  static OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(ZoneOffset.UTC);
  }
}
