package kr.co.axlink.standard.service;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.project.service.ProjectWriteGuard;
import kr.co.axlink.standard.domain.HistoryEntityType;
import kr.co.axlink.standard.domain.RequirementPriority;
import kr.co.axlink.standard.domain.RequirementStatus;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.history.EntityHistoryRecorder;
import kr.co.axlink.standard.repository.RequirementRepository;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.web.StandardDtos.EntityHistoryResponse;
import kr.co.axlink.standard.web.StandardDtos.EntityStatusUpdateRequest;
import kr.co.axlink.standard.web.StandardDtos.RequirementDetailResponse;
import kr.co.axlink.standard.web.StandardDtos.RequirementResponse;
import kr.co.axlink.standard.web.StandardDtos.SourceRef;
import kr.co.axlink.standard.web.StandardDtos.TraceLinkResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RequirementService {

  private final RequirementRepository requirementRepository;
  private final TraceQueryHelper traceQueryHelper;
  private final EntityHistoryRecorder historyRecorder;
  private final ProjectAccessResolver accessResolver;
  private final ProjectWriteGuard writeGuard;
  private final Clock clock;

  public RequirementService(RequirementRepository requirementRepository, TraceQueryHelper traceQueryHelper,
      EntityHistoryRecorder historyRecorder, ProjectAccessResolver accessResolver,
      ProjectWriteGuard writeGuard, Clock clock) {
    this.requirementRepository = requirementRepository;
    this.traceQueryHelper = traceQueryHelper;
    this.historyRecorder = historyRecorder;
    this.accessResolver = accessResolver;
    this.writeGuard = writeGuard;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public PageResponse<RequirementResponse> list(UUID projectId, RequirementStatus status,
      RequirementPriority priority, String q, PageQuery page, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    var sort = RequirementRepository.sort(page.sort());
    var rows = requirementRepository.search(projectId, status, priority, q, sort, page);
    long total = requirementRepository.countSearch(projectId, status, priority, q);
    List<UUID> ids = rows.stream().map(StandardRows.RequirementRow::id).toList();
    Map<UUID, Boolean> complete = traceQueryHelper.traceCompleteFlags(projectId, TraceEntityType.REQUIREMENT, ids);
    return PageResponse.of(rows.stream().map(r -> toResponse(r, complete.getOrDefault(r.id(), false))).toList(),
        page, total);
  }

  @Transactional(readOnly = true)
  public RequirementDetailResponse get(UUID requirementId, AuthPrincipal principal) {
    StandardRows.RequirementRow row = requirementRepository.findById(requirementId)
        .orElseThrow(() -> ApiExceptions.notFound("requirement", requirementId));
    accessResolver.requireProject(principal, row.projectId());
    boolean complete = traceQueryHelper.hasAnyTraceLink(row.projectId(), TraceEntityType.REQUIREMENT, row.id());
    List<TraceLinkResponse> links = traceQueryHelper.linksFor(row.projectId(), TraceEntityType.REQUIREMENT, row.id());
    List<EntityHistoryResponse> hist = traceQueryHelper.history(HistoryEntityType.REQUIREMENT, row.id());
    return new RequirementDetailResponse(row.id(), row.projectId(), row.code(), row.title(),
        row.priority(), row.status(), row.assignee(), toSourceRef(row), complete, row.updatedAt(),
        row.body(), links, hist);
  }

  @Transactional
  public RequirementResponse changeStatus(UUID requirementId, EntityStatusUpdateRequest req, AuthPrincipal principal) {
    StandardRows.RequirementRow row = requirementRepository.findById(requirementId)
        .orElseThrow(() -> ApiExceptions.notFound("requirement", requirementId));
    accessResolver.requireProject(principal, row.projectId());
    writeGuard.assertWritable(row.projectId());
    RequirementStatus next = parseStatus(req.status());
    if (!row.status().canTransitionTo(next)) {
      throw ApiExceptions.invalidTransition(row.status(), next);
    }
    Instant now = Instant.now(clock);
    requirementRepository.updateStatus(requirementId, next, now);
    historyRecorder.record(HistoryEntityType.REQUIREMENT, requirementId, row.projectId(),
        "status", row.status().name(), next.name(), actorOf(principal));
    if (req.note() != null && !req.note().isBlank()) {
      historyRecorder.record(HistoryEntityType.REQUIREMENT, requirementId, row.projectId(),
          "note", null, req.note(), actorOf(principal));
    }
    return toResponse(row.withStatus(next, Instant.now()), traceQueryHelper.hasAnyTraceLink(
        row.projectId(), TraceEntityType.REQUIREMENT, requirementId));
  }

  static String actorOf(AuthPrincipal p) {
    return p == null ? "system" : "user:" + p.userId();
  }

  static RequirementStatus parseStatus(String s) {
    try {
      return RequirementStatus.valueOf(s);
    } catch (Exception e) {
      throw ApiExceptions.validationFailed("알 수 없는 상태: " + s);
    }
  }

  static SourceRef toSourceRef(StandardRows.RequirementRow r) {
    return new SourceRef(r.sourceKind(), r.toolConnectionId(), r.externalId(), r.externalUrl());
  }

  static RequirementResponse toResponse(StandardRows.RequirementRow r, boolean traceComplete) {
    return new RequirementResponse(r.id(), r.projectId(), r.code(), r.title(), r.priority(),
        r.status(), r.assignee(), toSourceRef(r), traceComplete, r.updatedAt());
  }
}
