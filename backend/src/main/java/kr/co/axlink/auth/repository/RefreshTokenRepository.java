package kr.co.axlink.auth.repository;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.auth.domain.RefreshToken;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class RefreshTokenRepository {

  private static final String COLUMNS =
      "id, app_user_id, token_hash, expires_at, revoked_at, user_agent, created_at";

  private final JdbcClient jdbcClient;

  public RefreshTokenRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(UUID appUserId, String tokenHash, Instant expiresAt, String userAgent) {
    return jdbcClient.sql("""
        insert into refresh_token (app_user_id, token_hash, expires_at, user_agent)
        values (:appUserId, :tokenHash, :expiresAt, :userAgent)
        returning id
        """)
        .param("appUserId", appUserId)
        .param("tokenHash", tokenHash)
        .param("expiresAt", utc(expiresAt))
        .param("userAgent", userAgent)
        .query(UUID.class)
        .single();
  }

  public Optional<RefreshToken> findByTokenHash(String tokenHash) {
    return jdbcClient.sql("select " + COLUMNS + " from refresh_token where token_hash = :hash")
        .param("hash", tokenHash)
        .query(RefreshToken.class)
        .optional();
  }

  public int revoke(UUID id, Instant at) {
    return jdbcClient
        .sql("update refresh_token set revoked_at = :at where id = :id and revoked_at is null")
        .param("at", utc(at))
        .param("id", id)
        .update();
  }

  public int revokeAllByUser(UUID appUserId, Instant at) {
    return jdbcClient.sql("""
        update refresh_token set revoked_at = :at
         where app_user_id = :appUserId and revoked_at is null
        """)
        .param("at", utc(at))
        .param("appUserId", appUserId)
        .update();
  }

  public int deleteExpired(Instant before) {
    return jdbcClient.sql("delete from refresh_token where expires_at < :before")
        .param("before", utc(before))
        .update();
  }

  private static OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(ZoneOffset.UTC);
  }
}
