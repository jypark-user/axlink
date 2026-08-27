package kr.co.axlink.integration.web;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.integration.domain.SyncJob;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.SyncJobStatus;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.mapping.MappingRules;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolCredential;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolProbe;
import kr.co.axlink.integration.service.ToolConnectionService;
import kr.co.axlink.integration.service.ToolConnectionTestService;
import kr.co.axlink.integration.web.ToolConnectionDtos.CreateRequest;
import kr.co.axlink.integration.web.ToolConnectionDtos.CredentialRequest;
import kr.co.axlink.integration.web.ToolConnectionDtos.Response;
import kr.co.axlink.integration.web.ToolConnectionDtos.StatusUpdateRequest;
import kr.co.axlink.integration.web.ToolConnectionDtos.SyncTriggerRequest;
import kr.co.axlink.integration.web.ToolConnectionDtos.TestRequest;
import kr.co.axlink.integration.web.ToolConnectionDtos.TestResponse;
import kr.co.axlink.integration.web.ToolConnectionDtos.UpdateRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ToolConnectionController {

  private final ToolConnectionService connectionService;
  private final ToolConnectionTestService testService;
  private final JdbcClient jdbcClient;
  private final JsonCodec jsonCodec;

  public ToolConnectionController(ToolConnectionService connectionService,
      ToolConnectionTestService testService, JdbcClient jdbcClient, JsonCodec jsonCodec) {
    this.connectionService = connectionService;
    this.testService = testService;
    this.jdbcClient = jdbcClient;
    this.jsonCodec = jsonCodec;
  }

  @GetMapping("/projects/{projectId}/connections")
  public List<Response> list(@PathVariable UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    List<ToolConnection> connections = connectionService.findByProject(projectId, principal);
    List<Response> out = new ArrayList<>();
    for (ToolConnection c : connections) {
      out.add(toResponse(c));
    }
    return out;
  }

  @PostMapping("/projects/{projectId}/connections")
  public ResponseEntity<Response> create(@PathVariable UUID projectId,
      @RequestBody CreateRequest request,
      @AuthenticationPrincipal AuthPrincipal principal) {
    ToolCredential credential = buildCredential(request.tool(), request.credential());
    ToolConnection connection = connectionService.create(projectId, request.tool(),
        request.name(), request.baseUrl(), request.targetResource(), credential, principal);
    return ResponseEntity.status(HttpStatus.CREATED).body(toResponse(connection));
  }

  @GetMapping("/connections/{connectionId}")
  public Response get(@PathVariable UUID connectionId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return toResponse(connectionService.findOrThrow(connectionId));
  }

  @PatchMapping("/connections/{connectionId}")
  public Response update(@PathVariable UUID connectionId, @RequestBody UpdateRequest request,
      @AuthenticationPrincipal AuthPrincipal principal) {
    ToolCredential credential = request.credential() == null ? null
        : buildCredential(resolveToolForConnection(connectionId), request.credential());
    ToolConnection connection = connectionService.update(connectionId, request.name(),
        request.baseUrl(), request.targetResource(), credential, principal);
    return toResponse(connection);
  }

  @DeleteMapping("/connections/{connectionId}")
  public ResponseEntity<Void> delete(@PathVariable UUID connectionId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    connectionService.delete(connectionId, principal);
    return ResponseEntity.noContent().build();
  }

  @PatchMapping("/connections/{connectionId}/status")
  public Response updateStatus(@PathVariable UUID connectionId,
      @RequestBody StatusUpdateRequest request,
      @AuthenticationPrincipal AuthPrincipal principal) {
    ToolConnection connection = connectionService.changeStatus(connectionId, request.status(),
        principal);
    return toResponse(connection);
  }

  @PostMapping("/connections/test")
  public TestResponse testUnsaved(@RequestBody TestRequest request,
      @AuthenticationPrincipal AuthPrincipal principal) {
    ToolCredential credential = buildCredential(request.tool(), request.credential());
    ToolProbe probe = testService.test(request.tool(), request.baseUrl(), request.targetResource(),
        credential);
    return new TestResponse(probe.reachable(), probe.resourceName(), probe.detectedItemTypes(),
        java.time.Instant.now());
  }

  @PostMapping("/connections/{connectionId}/test")
  public TestResponse testSaved(@PathVariable UUID connectionId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    ToolProbe probe = testService.testSaved(connectionId, principal);
    return new TestResponse(probe.reachable(), probe.resourceName(), probe.detectedItemTypes(),
        java.time.Instant.now());
  }

  @PostMapping("/connections/{connectionId}/sync")
  public ResponseEntity<SyncJobDtos.Response> triggerSync(@PathVariable UUID connectionId,
      @RequestBody SyncTriggerRequest request,
      @AuthenticationPrincipal AuthPrincipal principal) {
    SyncJobKind kind = SyncJobKind.valueOf(request.kind());
    SyncJob job = connectionService.triggerSync(connectionId, kind, principal);
    return ResponseEntity.status(HttpStatus.ACCEPTED).body(toJobResponse(job));
  }

  private ToolType resolveToolForConnection(UUID connectionId) {
    return connectionService.findOrThrow(connectionId).tool();
  }

  /** GITHUB(Personal Access Token) · REDMINE(API Key) 둘 다 토큰 하나만 쓴다. */
  private ToolCredential buildCredential(ToolType tool, CredentialRequest cred) {
    if (cred == null) {
      throw ApiExceptions.validationFailed("credential 이 필요합니다.");
    }
    if (cred.accessToken() == null || cred.accessToken().isBlank()) {
      throw ApiExceptions.validationFailed(tool + " 연결은 accessToken 이 필요합니다.");
    }
    return new ToolCredential(null, cred.accessToken());
  }

  private Response toResponse(ToolConnection c) {
    int ingested = jdbcClient.sql(
        "select count(*) from raw_artifact where tool_connection_id = :id")
        .param("id", c.id()).query(Integer.class).single();
    String lastStatus = jdbcClient.sql("""
        select status from sync_job where tool_connection_id = :id
          order by started_at desc nulls last limit 1
        """)
        .param("id", c.id()).query(String.class).optional().orElse(null);
    SyncJobStatus lastSyncStatus = lastStatus == null ? null
        : SyncJobStatus.valueOf(lastStatus);
    MappingRules rules = jsonCodec.read(c.mappingRulesJson(), MappingRules.class);
    int ruleCount = rules == null || rules.rules() == null ? 0 : rules.rules().size();
    return new Response(
        c.id().toString(), c.projectId().toString(), c.tool(), c.name(), c.baseUrl(),
        c.targetResource(), c.authHint(), c.status(), c.lastSyncedAt(), lastSyncStatus,
        c.lastError(), ingested, ruleCount, c.createdAt());
  }

  private SyncJobDtos.Response toJobResponse(SyncJob job) {
    ToolConnection c = connectionService.findOrThrow(job.toolConnectionId());
    SyncJobDtos.Stats stats = jsonCodec.read(job.statsJson(), SyncJobDtos.Stats.class);
    return new SyncJobDtos.Response(
        job.id().toString(), c.id().toString(), c.name(), c.projectId().toString(), c.tool(),
        job.kind(), job.status(), job.startedAt(), job.finishedAt(), stats, job.error(),
        job.status() == SyncJobStatus.FAILED);
  }
}
