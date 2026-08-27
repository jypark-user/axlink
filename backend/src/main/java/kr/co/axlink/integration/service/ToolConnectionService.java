package kr.co.axlink.integration.service;

import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.integration.domain.SyncJob;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.domain.ToolConnectionStatus;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.mapping.MappingRuleDefaults;
import kr.co.axlink.integration.mapping.MappingRules;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolCredential;
import kr.co.axlink.integration.repository.ToolConnectionRepository;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class ToolConnectionService {

  private final ProjectAccessResolver accessResolver;
  private final ToolConnectionRepository connectionRepository;
  private final ToolConnectionSecretProvider secretProvider;
  private final SyncJobService syncJobService;
  private final SyncDispatcher syncDispatcher;
  private final JsonCodec jsonCodec;
  private final JdbcClient jdbcClient;

  public ToolConnectionService(ProjectAccessResolver accessResolver,
      ToolConnectionRepository connectionRepository,
      ToolConnectionSecretProvider secretProvider, SyncJobService syncJobService,
      SyncDispatcher syncDispatcher, JsonCodec jsonCodec, JdbcClient jdbcClient) {
    this.accessResolver = accessResolver;
    this.connectionRepository = connectionRepository;
    this.secretProvider = secretProvider;
    this.syncJobService = syncJobService;
    this.syncDispatcher = syncDispatcher;
    this.jsonCodec = jsonCodec;
    this.jdbcClient = jdbcClient;
  }

  public ToolConnection create(UUID projectId, ToolType tool, String name, String baseUrl,
      String targetResource, ToolCredential credential, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    requireProjectOpen(projectId);
    requireHttps(baseUrl);
    String encrypted = secretProvider.encrypt(credential);
    String hint = secretProvider.hint(credential);
    MappingRules seed = MappingRuleDefaults.seedFor(tool, List.of());
    ToolConnection connection = new ToolConnection(
        null, projectId, principal.organizationId(), tool, name, baseUrl, targetResource,
        encrypted, hint, jsonCodec.write(seed), null, ToolConnectionStatus.DRAFT,
        null, null, null, null, null, null);
    UUID id = connectionRepository.insert(connection);
    SyncJob job = syncJobService.enqueue(id, SyncJobKind.BACKFILL, null);
    syncDispatcher.dispatch(job.id());
    return findOrThrow(id);
  }

  public ToolConnection update(UUID connectionId, String name, String baseUrl,
      String targetResource, ToolCredential credential, AuthPrincipal principal) {
    ToolConnection existing = findOrThrow(connectionId);
    accessResolver.requireProject(principal, existing.projectId());
    requireProjectOpen(existing.projectId());
    String newName = name == null ? existing.name() : name;
    String newBase = baseUrl == null ? existing.baseUrl() : baseUrl;
    if (baseUrl != null) {
      requireHttps(baseUrl);
    }
    String newTarget = targetResource == null ? existing.targetResource() : targetResource;
    String encrypted = existing.authEncrypted();
    String hint = existing.authHint();
    if (credential != null && credential.secret() != null && !credential.secret().isBlank()) {
      encrypted = secretProvider.encrypt(credential);
      hint = secretProvider.hint(credential);
    }
    connectionRepository.updateAuth(connectionId, encrypted, hint, newName, newBase, newTarget);
    return findOrThrow(connectionId);
  }

  public void delete(UUID connectionId, AuthPrincipal principal) {
    ToolConnection existing = findOrThrow(connectionId);
    accessResolver.requireProject(principal, existing.projectId());
    if (hasRunningJob(connectionId)) {
      throw ApiExceptions.syncJobConflict(connectionId);
    }
    connectionRepository.delete(connectionId);
  }

  public ToolConnection changeStatus(UUID connectionId, ToolConnectionStatus target,
      AuthPrincipal principal) {
    ToolConnection existing = findOrThrow(connectionId);
    accessResolver.requireProject(principal, existing.projectId());
    ToolConnectionStatus current = existing.status();
    if (target == ToolConnectionStatus.ACTIVE) {
      if (current != ToolConnectionStatus.VERIFIED && current != ToolConnectionStatus.PAUSED) {
        throw ApiExceptions.invalidTransition(current, target);
      }
    } else if (target == ToolConnectionStatus.PAUSED) {
      if (current != ToolConnectionStatus.ACTIVE) {
        throw ApiExceptions.invalidTransition(current, target);
      }
    } else {
      throw ApiExceptions.invalidTransition(current, target);
    }
    connectionRepository.updateStatus(connectionId, target, existing.lastError());
    return findOrThrow(connectionId);
  }

  public ToolConnection markVerified(UUID connectionId) {
    ToolConnection existing = findOrThrow(connectionId);
    if (existing.status() == ToolConnectionStatus.DRAFT
        || existing.status() == ToolConnectionStatus.FAILED) {
      connectionRepository.updateStatus(connectionId, ToolConnectionStatus.VERIFIED,
          existing.lastError());
      connectionRepository.updateLastVerified(connectionId, java.time.Instant.now());
    }
    return findOrThrow(connectionId);
  }

  public List<ToolConnection> findByProject(UUID projectId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    return connectionRepository.findByProjectId(projectId);
  }

  public SyncJob triggerSync(UUID connectionId, SyncJobKind kind, AuthPrincipal principal) {
    ToolConnection existing = findOrThrow(connectionId);
    accessResolver.requireProject(principal, existing.projectId());
    requireProjectOpen(existing.projectId());
    if (hasRunningJob(connectionId)) {
      throw ApiExceptions.syncJobConflict(connectionId);
    }
    SyncJob job = syncJobService.enqueue(connectionId, kind, null);
    syncDispatcher.dispatch(job.id());
    return job;
  }

  public ToolConnection findOrThrow(UUID connectionId) {
    return connectionRepository.findById(connectionId)
        .orElseThrow(() -> ApiExceptions.notFound("tool_connection", connectionId));
  }

  public MappingRules getMappingRules(UUID connectionId, AuthPrincipal principal) {
    ToolConnection connection = findOrThrow(connectionId);
    accessResolver.requireProject(principal, connection.projectId());
    MappingRules rules = jsonCodec.read(connection.mappingRulesJson(), MappingRules.class);
    return rules == null ? new MappingRules(1, List.of()) : rules;
  }

  public MappingRules replaceMappingRules(UUID connectionId, MappingRules rules,
      boolean reapplyNow, AuthPrincipal principal) {
    ToolConnection connection = findOrThrow(connectionId);
    accessResolver.requireProject(principal, connection.projectId());
    if (rules == null) {
      rules = new MappingRules(1, List.of());
    }
    connectionRepository.updateMappingRules(connectionId, jsonCodec.write(rules));
    if (reapplyNow) {
      SyncJob job = syncJobService.enqueue(connectionId, SyncJobKind.BACKFILL, null);
      syncDispatcher.dispatch(job.id());
    }
    return getMappingRules(connectionId, principal);
  }

  private boolean hasRunningJob(UUID connectionId) {
    return jdbcClient.sql("""
        select 1 from sync_job where tool_connection_id = :id and status = 'RUNNING' limit 1
        """)
        .param("id", connectionId).query(Integer.class).list().size() > 0;
  }

  private void requireProjectOpen(UUID projectId) {
    String status = jdbcClient.sql("select status from project where id = :id")
        .param("id", projectId).query(String.class).optional().orElse(null);
    if (status == null) {
      throw ApiExceptions.notFound("project", projectId);
    }
    if ("CLOSED".equals(status)) {
      throw ApiExceptions.projectClosed(projectId);
    }
  }

  private void requireHttps(String baseUrl) {
    if (baseUrl == null || !baseUrl.startsWith("https://")) {
      throw ApiExceptions.validationFailed("baseUrl 은 https 로 시작해야 합니다.");
    }
  }
}
