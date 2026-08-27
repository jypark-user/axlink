package kr.co.axlink.org.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.org.domain.UserInvitation;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class UserInvitationRepository {

  private static final String COLUMNS =
      "id, app_user_id, token_hash, expires_at, accepted_at, invited_by_user_id, created_at";

  private final JdbcClient jdbcClient;

  public UserInvitationRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(UUID appUserId, String tokenHash, Instant expiresAt, UUID invitedByUserId) {
    return jdbcClient.sql("""
        insert into user_invitation (app_user_id, token_hash, expires_at, invited_by_user_id)
        values (:appUserId, :tokenHash, :expiresAt, :invitedByUserId)
        returning id
        """)
        .param("appUserId", appUserId)
        .param("tokenHash", tokenHash)
        .param("expiresAt", utc(expiresAt))
        .param("invitedByUserId", invitedByUserId)
        .query(UUID.class)
        .single();
  }

  public Optional<UserInvitation> findByTokenHash(String tokenHash) {
    return jdbcClient.sql("select " + COLUMNS + " from user_invitation where token_hash = :hash")
        .param("hash", tokenHash)
        .query(this::map)
        .optional();
  }

  public int markAccepted(UUID id, Instant at) {
    return jdbcClient.sql("""
        update user_invitation set accepted_at = :at, updated_at = now()
         where id = :id and accepted_at is null
        """)
        .param("id", id)
        .param("at", utc(at))
        .update();
  }

  /** 새 링크를 발급할 때 이전 링크를 죽인다. */
  public int expireOpen(UUID appUserId, Instant at) {
    return jdbcClient.sql("""
        update user_invitation set expires_at = :at, updated_at = now()
         where app_user_id = :appUserId and accepted_at is null and expires_at > :at
        """)
        .param("appUserId", appUserId)
        .param("at", utc(at))
        .update();
  }

  private UserInvitation map(ResultSet rs, int rowNum) throws SQLException {
    return new UserInvitation(
        rs.getObject("id", UUID.class),
        rs.getObject("app_user_id", UUID.class),
        rs.getString("token_hash"),
        toInstant(rs, "expires_at"),
        toInstant(rs, "accepted_at"),
        rs.getObject("invited_by_user_id", UUID.class),
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
