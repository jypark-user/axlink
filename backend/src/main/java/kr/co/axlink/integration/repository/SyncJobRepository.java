package kr.co.axlink.integration.repository;

import java.time.Instant;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.integration.domain.SyncJob;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.SyncJobStatus;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SyncJobRepository {

  private final JdbcClient jdbcClient;

  public SyncJobRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insertQueued(UUID connectionId, SyncJobKind kind, Instant cursorFrom,
      Instant cursorTo, UUID retryOfJobId) {
    String sql = """
        insert into sync_job (tool_connection_id, kind, status, cursor_from, cursor_to,
            retry_of_job_id)
        values (:connectionId, :kind, 'QUEUED', :cursorFrom, :cursorTo, :retryOfJobId)
        returning id
        """;
    return jdbcClient.sql(sql)
        .param("connectionId", connectionId)
        .param("kind", kind.name())
        .param("cursorFrom", utc(cursorFrom))
        .param("cursorTo", utc(cursorTo))
        .param("retryOfJobId", retryOfJobId)
        .query(UUID.class).single();
  }

  public Optional<UUID> markRunning(UUID jobId) {
    try {
      return jdbcClient.sql("""
          update sync_job set status = 'RUNNING', started_at = now(), updated_at = now()
           where id = :jobId and status = 'QUEUED'
          returning id
          """)
          .param("jobId", jobId)
          .query(UUID.class).optional();
    } catch (DuplicateKeyException e) {
      return Optional.empty();
    }
  }

  public int markSucceeded(UUID jobId, String statsJson, Instant cursorTo) {
    return jdbcClient.sql("""
        update sync_job set status = 'SUCCEEDED', finished_at = now(),
            cursor_to = :cursorTo, stats_json = :statsJson::jsonb, error_code = null,
            error = null, updated_at = now()
         where id = :jobId
        """)
        .param("jobId", jobId).param("statsJson", statsJson)
        .param("cursorTo", utc(cursorTo))
        .update();
  }

  public int markFailed(UUID jobId, String errorCode, String error, String statsJson) {
    return jdbcClient.sql("""
        update sync_job set status = 'FAILED', finished_at = now(),
            error_code = :errorCode, error = :error, stats_json = :statsJson::jsonb, updated_at = now()
         where id = :jobId
        """)
        .param("jobId", jobId).param("errorCode", errorCode).param("error", error)
        .param("statsJson", statsJson)
        .update();
  }

  public int markCancelled(UUID jobId) {
    return jdbcClient.sql("""
        update sync_job set status = 'CANCELLED', finished_at = now(), updated_at = now()
         where id = :jobId and status in ('QUEUED','RUNNING')
        """)
        .param("jobId", jobId).update();
  }

  public Optional<SyncJob> findById(UUID id) {
    return jdbcClient.sql("select * from sync_job where id = :id")
        .param("id", id).query(SyncJob.class).optional();
  }

  public List<SyncJob> search(Collection<UUID> projectIds, UUID connectionId,
      SyncJobStatus status, SyncJobKind kind, String orderByClause, int limit, int offset) {
    StringBuilder sql = new StringBuilder("""
        select sj.* from sync_job sj
          join tool_connection tc on tc.id = sj.tool_connection_id
         where tc.project_id in (:projectIds)
        """);
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectIds", projectIds);
    if (connectionId != null) {
      sql.append(" and sj.tool_connection_id = :connectionId");
      params.put("connectionId", connectionId);
    }
    if (status != null) {
      sql.append(" and sj.status = :status");
      params.put("status", status.name());
    }
    if (kind != null) {
      sql.append(" and sj.kind = :kind");
      params.put("kind", kind.name());
    }
    sql.append(" order by ").append(orderByClause);
    sql.append(" limit :limit offset :offset");
    params.put("limit", limit);
    params.put("offset", offset);
    return jdbcClient.sql(sql.toString()).params(params).query(SyncJob.class).list();
  }

  public long countSearch(Collection<UUID> projectIds, UUID connectionId, SyncJobStatus status,
      SyncJobKind kind) {
    StringBuilder sql = new StringBuilder("""
        select count(*) from sync_job sj
          join tool_connection tc on tc.id = sj.tool_connection_id
         where tc.project_id in (:projectIds)
        """);
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectIds", projectIds);
    if (connectionId != null) {
      sql.append(" and sj.tool_connection_id = :connectionId");
      params.put("connectionId", connectionId);
    }
    if (status != null) {
      sql.append(" and sj.status = :status");
      params.put("status", status.name());
    }
    if (kind != null) {
      sql.append(" and sj.kind = :kind");
      params.put("kind", kind.name());
    }
    return jdbcClient.sql(sql.toString()).params(params).query(Long.class).single();
  }

  public int deleteSucceededBefore(Instant cutoff) {
    return jdbcClient.sql("""
        delete from sync_job where status = 'SUCCEEDED' and finished_at < :cutoff
        """)
        .param("cutoff", utc(cutoff)).update();
  }

  private static java.time.OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(java.time.ZoneOffset.UTC);
  }
}
