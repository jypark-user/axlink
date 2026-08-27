package kr.co.axlink.integration.web;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.integration.domain.SyncJob;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.SyncJobStatus;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.repository.SyncJobRepository;
import kr.co.axlink.integration.service.SyncDispatcher;
import kr.co.axlink.integration.service.SyncJobService;
import kr.co.axlink.integration.service.ToolConnectionService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class SyncJobController {

  private static final Map<String, String> SORT_WHITELIST = Map.of(
      "startedAt", "sj.started_at", "finishedAt", "sj.finished_at");

  private final SyncJobService syncJobService;
  private final SyncJobRepository syncJobRepository;
  private final ToolConnectionService connectionService;
  private final ProjectAccessResolver accessResolver;
  private final SyncDispatcher syncDispatcher;
  private final JsonCodec jsonCodec;

  public SyncJobController(SyncJobService syncJobService, SyncJobRepository syncJobRepository,
      ToolConnectionService connectionService, ProjectAccessResolver accessResolver,
      SyncDispatcher syncDispatcher, JsonCodec jsonCodec) {
    this.syncJobService = syncJobService;
    this.syncJobRepository = syncJobRepository;
    this.connectionService = connectionService;
    this.accessResolver = accessResolver;
    this.syncDispatcher = syncDispatcher;
    this.jsonCodec = jsonCodec;
  }

  @GetMapping("/sync-jobs")
  public PageResponse<SyncJobDtos.Response> list(
      @RequestParam(required = false) UUID projectId,
      @RequestParam(required = false) UUID connectionId,
      @RequestParam(required = false) SyncJobStatus status,
      @RequestParam(required = false) SyncJobKind kind,
      PageQuery pageQuery,
      @AuthenticationPrincipal AuthPrincipal principal) {
    Set<UUID> scope = projectId == null
        ? accessResolver.allowedProjectIds(principal)
        : Set.copyOf(accessResolver.resolveScope(principal, List.of(projectId)));
    if (scope.isEmpty()) {
      return PageResponse.of(List.of(), pageQuery, 0);
    }
    SortSpec sort = SortSpec.parse(pageQuery.sort(), SORT_WHITELIST, "sj.started_at desc");
    List<SyncJob> jobs = syncJobRepository.search(scope, connectionId, status, kind,
        sort.toOrderByClause(), pageQuery.limit(), pageQuery.offset());
    long total = syncJobRepository.countSearch(scope, connectionId, status, kind);
    Map<UUID, ToolConnection> connections = loadConnections(jobs);
    List<SyncJobDtos.Response> content = jobs.stream()
        .map(j -> toResponse(j, connections.get(j.toolConnectionId())))
        .toList();
    return PageResponse.of(content, pageQuery, total);
  }

  @GetMapping("/sync-jobs/{syncJobId}")
  public SyncJobDtos.Response get(@PathVariable UUID syncJobId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    SyncJob job = syncJobService.findOrThrow(syncJobId);
    ToolConnection connection = connectionService.findOrThrow(job.toolConnectionId());
    accessResolver.requireProject(principal, connection.projectId());
    return toResponse(job, connection);
  }

  @PostMapping("/sync-jobs/{syncJobId}/retry")
  public SyncJobDtos.Response retry(@PathVariable UUID syncJobId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    SyncJob original = syncJobService.findOrThrow(syncJobId);
    ToolConnection connection = connectionService.findOrThrow(original.toolConnectionId());
    accessResolver.requireProject(principal, connection.projectId());
    SyncJob retried = syncJobService.retry(syncJobId);
    syncDispatcher.dispatch(retried.id());
    return toResponse(retried, connection);
  }

  @PostMapping("/sync-jobs/{syncJobId}/cancel")
  public SyncJobDtos.Response cancel(@PathVariable UUID syncJobId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    SyncJob original = syncJobService.findOrThrow(syncJobId);
    ToolConnection connection = connectionService.findOrThrow(original.toolConnectionId());
    accessResolver.requireProject(principal, connection.projectId());
    SyncJob cancelled = syncJobService.cancel(syncJobId);
    return toResponse(cancelled, connection);
  }

  private Map<UUID, ToolConnection> loadConnections(List<SyncJob> jobs) {
    Map<UUID, ToolConnection> map = new HashMap<>();
    for (SyncJob job : jobs) {
      UUID cid = job.toolConnectionId();
      if (!map.containsKey(cid)) {
        try {
          map.put(cid, connectionService.findOrThrow(cid));
        } catch (Exception ignored) {
        }
      }
    }
    return map;
  }

  private SyncJobDtos.Response toResponse(SyncJob job, ToolConnection connection) {
    SyncJobDtos.Stats stats = connection == null ? null
        : jsonCodec.read(job.statsJson(), SyncJobDtos.Stats.class);
    String connectionName = connection == null ? null : connection.name();
    String projectId = connection == null ? null : connection.projectId().toString();
    ToolType tool = connection == null ? null : connection.tool();
    return new SyncJobDtos.Response(
        job.id().toString(), job.toolConnectionId().toString(), connectionName, projectId, tool,
        job.kind(), job.status(), job.startedAt(), job.finishedAt(), stats, job.error(),
        job.status() == SyncJobStatus.FAILED);
  }
}
