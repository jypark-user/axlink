package kr.co.axlink.standard.service;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.project.service.ProjectWriteGuard;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.domain.TraceLinkDraft;
import kr.co.axlink.standard.domain.TraceLinkKind;
import kr.co.axlink.standard.domain.TraceLinkOrigin;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.repository.TraceLinkRepository;
import kr.co.axlink.standard.web.StandardDtos.TraceLinkCreateRequest;
import kr.co.axlink.standard.web.StandardDtos.TraceLinkResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TraceLinkService {

  private final TraceLinkRepository traceLinkRepository;
  private final TraceQueryHelper traceQueryHelper;
  private final ProjectAccessResolver accessResolver;
  private final ProjectWriteGuard writeGuard;
  private final Clock clock;

  public TraceLinkService(TraceLinkRepository traceLinkRepository, TraceQueryHelper traceQueryHelper,
      ProjectAccessResolver accessResolver, ProjectWriteGuard writeGuard, Clock clock) {
    this.traceLinkRepository = traceLinkRepository;
    this.traceQueryHelper = traceQueryHelper;
    this.accessResolver = accessResolver;
    this.writeGuard = writeGuard;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public PageResponse<TraceLinkResponse> list(UUID projectId, TraceEntityType fromType,
      TraceLinkKind linkKind, PageQuery page, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    var sort = TraceLinkRepository.sort(page.sort());
    var rows = traceLinkRepository.search(projectId, fromType, linkKind, sort, page);
    long total = traceLinkRepository.countSearch(projectId, fromType, linkKind);
    Map<UUID, String> labels = new LinkedHashMap<>();
    return PageResponse.of(rows.stream().map(r -> toResponse(r, labels)).toList(), page, total);
  }

  @Transactional
  public TraceLinkResponse createManual(UUID projectId, TraceLinkCreateRequest req, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    writeGuard.assertWritable(projectId);
    if (!traceLinkRepository.entityExists(projectId, req.fromType(), req.fromId())) {
      throw ApiExceptions.validationFailed("존재하지 않는 from 엔티티: " + req.fromType() + ":" + req.fromId());
    }
    if (!traceLinkRepository.entityExists(projectId, req.toType(), req.toId())) {
      throw ApiExceptions.validationFailed("존재하지 않는 to 엔티티: " + req.toType() + ":" + req.toId());
    }
    if (req.fromType() == req.toType() && req.fromId().equals(req.toId())) {
      throw ApiExceptions.validationFailed("자기 자신으로의 링크는 허용되지 않습니다.");
    }
    Instant now = Instant.now(clock);
    UUID id = traceLinkRepository.insert(projectId, req.fromType(), req.fromId(), req.toType(),
        req.toId(), req.linkKind(), TraceLinkOrigin.MANUAL, principal.userId(), now);
    if (id == null) {
      throw ApiExceptions.duplicate("trace_link", req.fromType() + ":" + req.fromId() + "->" + req.toType());
    }
    return toResponse(traceLinkRepository.findById(id).orElseThrow(), new LinkedHashMap<>());
  }

  @Transactional
  public int createAuto(UUID projectId, List<TraceLinkDraft> drafts) {
    int created = 0;
    Instant now = Instant.now(clock);
    for (TraceLinkDraft d : drafts) {
      if (!traceLinkRepository.entityExists(projectId, d.fromType(), d.fromId())
          || !traceLinkRepository.entityExists(projectId, d.toType(), d.toId())) {
        continue;
      }
      UUID id = traceLinkRepository.insert(projectId, d.fromType(), d.fromId(), d.toType(),
          d.toId(), d.linkKind(), TraceLinkOrigin.AUTO, null, now);
      if (id != null) {
        created++;
      }
    }
    return created;
  }

  @Transactional
  public void delete(UUID traceLinkId, AuthPrincipal principal) {
    StandardRows.TraceLinkRow row = traceLinkRepository.findById(traceLinkId)
        .orElseThrow(() -> ApiExceptions.notFound("trace_link", traceLinkId));
    accessResolver.requireProject(principal, row.projectId());
    writeGuard.assertWritable(row.projectId());
    traceLinkRepository.delete(traceLinkId, principal.userId(), Instant.now(clock));
  }

  private TraceLinkResponse toResponse(StandardRows.TraceLinkRow r, Map<UUID, String> labels) {
    return new TraceLinkResponse(r.id(), r.projectId(), r.fromType(), r.fromId(),
        traceQueryHelper.labelOf(r.projectId(), r.fromType(), r.fromId(), labels),
        r.toType(), r.toId(),
        traceQueryHelper.labelOf(r.projectId(), r.toType(), r.toId(), labels),
        r.linkKind(), r.origin(), r.status(), null, r.createdAt());
  }
}
