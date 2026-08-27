package kr.co.axlink.project.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.project.domain.ProjectInvite;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ProjectInviteRepository {

  private static final String COLUMNS =
      "id, project_id, token_hash, expires_at, revoked_at, created_by_user_id, created_at";

  private final JdbcClient jdbcClient;

  public ProjectInviteRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(ProjectInvite i) {
    return jdbcClient.sql("""
        insert into project_invite (project_id, token_hash, expires_at, created_by_user_id)
        values (:projectId, :tokenHash, :expiresAt, :createdByUserId)
        returning id
        """)
        .param("projectId", i.projectId())
        .param("tokenHash", i.tokenHash())
        .param("expiresAt", utc(i.expiresAt()))
        .param("createdByUserId", i.createdByUserId())
        .query(UUID.class)
        .single();
  }

  public Optional<ProjectInvite> findById(UUID id) {
    return jdbcClient.sql("select " + COLUMNS + " from project_invite where id = :id")
        .param("id", id)
        .query(this::map)
        .optional();
  }

  public Optional<ProjectInvite> findByTokenHash(String tokenHash) {
    return jdbcClient.sql("select " + COLUMNS + " from project_invite where token_hash = :hash")
        .param("hash", tokenHash)
        .query(this::map)
        .optional();
  }

  public int revoke(UUID id, Instant at) {
    return jdbcClient.sql("""
        update project_invite set revoked_at = :at, updated_at = now()
         where id = :id and revoked_at is null
        """)
        .param("id", id)
        .param("at", utc(at))
        .update();
  }

  private ProjectInvite map(ResultSet rs, int rowNum) throws SQLException {
    return new ProjectInvite(
        rs.getObject("id", UUID.class),
        rs.getObject("project_id", UUID.class),
        rs.getString("token_hash"),
        toInstant(rs, "expires_at"),
        toInstant(rs, "revoked_at"),
        rs.getObject("created_by_user_id", UUID.class),
        toInstant(rs, "created_at"));
  }

  private static Instant toInstant(ResultSet rs, String column) throws SQLException {
    OffsetDateTime odt = rs.getObject(column, OffsetDateTime.class);
    return odt == null ? null : odt.toInstant();
  }

  private static OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(ZoneOffset.UTC);
  }
}
