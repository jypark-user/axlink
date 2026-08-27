package kr.co.axlink.integration.repository;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class RawArtifactRepository {

  private final JdbcClient jdbcClient;

  public RawArtifactRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public int upsert(UUID connectionId, String externalId, String objectKind, String payloadJson,
      String contentHash, Instant fetchedAt, UUID syncJobId) {
    String sql = """
        insert into raw_artifact (id, tool_connection_id, external_id, object_kind,
            payload_jsonb, content_hash, fetched_at, sync_job_id)
        values (gen_random_uuid(), :connectionId, :externalId, :objectKind,
            :payloadJson::jsonb, :contentHash, :fetchedAt, :syncJobId)
        on conflict (tool_connection_id, external_id) do update set
            object_kind = excluded.object_kind, payload_jsonb = excluded.payload_jsonb,
            content_hash = excluded.content_hash, fetched_at = excluded.fetched_at,
            sync_job_id = excluded.sync_job_id, created_at = now()
          where raw_artifact.content_hash is distinct from excluded.content_hash
        """;
    return jdbcClient.sql(sql)
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .param("objectKind", objectKind)
        .param("payloadJson", payloadJson)
        .param("contentHash", contentHash)
        .param("fetchedAt", utc(fetchedAt))
        .param("syncJobId", syncJobId)
        .update();
  }

  public Optional<String> findContentHash(UUID connectionId, String externalId) {
    return jdbcClient.sql("""
        select content_hash from raw_artifact
         where tool_connection_id = :connectionId and external_id = :externalId
        """)
        .param("connectionId", connectionId)
        .param("externalId", externalId)
        .query(String.class).optional();
  }

  private static java.time.OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(java.time.ZoneOffset.UTC);
  }
}
