package kr.co.axlink.integration.repository;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.domain.ToolConnectionStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ToolConnectionRepository {

  private final JdbcClient jdbcClient;

  public ToolConnectionRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(ToolConnection c) {
    String sql = """
        insert into tool_connection (project_id, contractor_org_id, tool, name, base_url,
            target_resource, auth_encrypted, auth_hint, mapping_rules_json, status)
        values (:projectId, :contractorOrgId, :tool, :name, :baseUrl,
            :targetResource, :authEncrypted, :authHint, :mappingRulesJson::jsonb, :status)
        returning id
        """;
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("projectId", c.projectId());
    params.put("contractorOrgId", c.contractorOrgId());
    params.put("tool", c.tool().name());
    params.put("name", c.name());
    params.put("baseUrl", c.baseUrl());
    params.put("targetResource", c.targetResource());
    params.put("authEncrypted", c.authEncrypted());
    params.put("authHint", c.authHint());
    params.put("mappingRulesJson", c.mappingRulesJson());
    params.put("status", c.status().name());
    return jdbcClient.sql(sql).params(params).query(UUID.class).single();
  }

  public Optional<ToolConnection> findById(UUID id) {
    return jdbcClient.sql("select * from tool_connection where id = :id")
        .param("id", id)
        .query(ToolConnection.class).optional();
  }

  public List<ToolConnection> findByProjectId(UUID projectId) {
    return jdbcClient.sql("select * from tool_connection where project_id = :projectId "
        + "order by created_at")
        .param("projectId", projectId)
        .query(ToolConnection.class).list();
  }

  public List<ToolConnection> findPollable(Instant dueBefore) {
    return jdbcClient.sql("""
        select tc.* from tool_connection tc
          join project p on p.id = tc.project_id
         where tc.status = 'ACTIVE' and p.status <> 'CLOSED'
           and (tc.last_synced_at is null or tc.last_synced_at < :dueBefore)
         order by tc.last_synced_at nulls first
        """)
        .param("dueBefore", utc(dueBefore))
        .query(ToolConnection.class).list();
  }

  public int updateCursor(UUID id, Instant lastSyncedAt, String cursor) {
    return jdbcClient.sql("""
        update tool_connection set last_synced_at = :lastSyncedAt,
            last_sync_cursor = :cursor, updated_at = now()
         where id = :id
        """)
        .param("id", id).param("lastSyncedAt", utc(lastSyncedAt)).param("cursor", cursor)
        .update();
  }

  public int updateStatus(UUID id, ToolConnectionStatus status, String lastError) {
    return jdbcClient.sql("""
        update tool_connection set status = :status, last_error = :lastError,
            updated_at = now()
         where id = :id
        """)
        .param("id", id).param("status", status.name()).param("lastError", lastError)
        .update();
  }

  public int updateLastVerified(UUID id, Instant verifiedAt) {
    return jdbcClient.sql("""
        update tool_connection set last_verified_at = :verifiedAt, updated_at = now()
         where id = :id
        """)
        .param("id", id).param("verifiedAt", utc(verifiedAt))
        .update();
  }

  public int updateMappingRules(UUID id, String json) {
    return jdbcClient.sql("""
        update tool_connection set mapping_rules_json = :json::jsonb, updated_at = now()
         where id = :id
        """)
        .param("id", id).param("json", json)
        .update();
  }

  public int updateAuth(UUID id, String authEncrypted, String authHint, String name,
      String baseUrl, String targetResource) {
    return jdbcClient.sql("""
        update tool_connection set auth_encrypted = :authEncrypted, auth_hint = :authHint,
            name = :name, base_url = :baseUrl, target_resource = :targetResource, updated_at = now()
         where id = :id
        """)
        .param("id", id).param("authEncrypted", authEncrypted).param("authHint", authHint)
        .param("name", name).param("baseUrl", baseUrl).param("targetResource", targetResource)
        .update();
  }

  public int delete(UUID id) {
    return jdbcClient.sql("delete from tool_connection where id = :id")
        .param("id", id).update();
  }

  private static java.time.OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(java.time.ZoneOffset.UTC);
  }
}
