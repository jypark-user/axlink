package kr.co.axlink.standard.service;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.project.service.ProjectWriteGuard;
import kr.co.axlink.standard.domain.AcceptanceStatus;
import kr.co.axlink.standard.domain.ChangeRequestStatus;
import kr.co.axlink.standard.domain.CorrectionStatus;
import kr.co.axlink.standard.domain.HistoryEntityType;
import kr.co.axlink.standard.history.EntityHistoryRecorder;
import kr.co.axlink.standard.repository.ChangeRequestRepository;
import kr.co.axlink.standard.repository.CorrectionActionRepository;
import kr.co.axlink.standard.repository.GovernanceRepository;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.web.StandardDtos.AcceptanceRecordCreateRequest;
import kr.co.axlink.standard.web.StandardDtos.AcceptanceRecordResponse;
import kr.co.axlink.standard.web.StandardDtos.ChangeRequestResponse;
import kr.co.axlink.standard.web.StandardDtos.CorrectionActionResponse;
import kr.co.axlink.standard.web.StandardDtos.EntityStatusUpdateRequest;
import kr.co.axlink.standard.web.StandardDtos.ProgressRecordResponse;
import kr.co.axlink.standard.web.StandardDtos.SourceRef;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GovernanceService {

  private final ChangeRequestRepository changeRequestRepository;
  private final CorrectionActionRepository correctionActionRepository;
  private final GovernanceRepository governanceRepository;
  private final ProjectAccessResolver accessResolver;
  private final ProjectWriteGuard writeGuard;
  private final EntityHistoryRecorder historyRecorder;
  private final JdbcClient jdbc;
  private final Clock clock;

  public GovernanceService(ChangeRequestRepository changeRequestRepository,
      CorrectionActionRepository correctionActionRepository, GovernanceRepository governanceRepository,
      ProjectAccessResolver accessResolver, ProjectWriteGuard writeGuard,
      EntityHistoryRecorder historyRecorder, JdbcClient jdbc, Clock clock) {
    this.changeRequestRepository = changeRequestRepository;
    this.correctionActionRepository = correctionActionRepository;
    this.governanceRepository = governanceRepository;
    this.accessResolver = accessResolver;
    this.writeGuard = writeGuard;
    this.historyRecorder = historyRecorder;
    this.jdbc = jdbc;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public PageResponse<ChangeRequestResponse> listChangeRequests(UUID projectId, PageQuery page, AuthPrincipal p) {
    accessResolver.requireProject(p, projectId);
    var sort = ChangeRequestRepository.sort(page.sort());
    var rows = changeRequestRepository.search(projectId, sort, page);
    long total = changeRequestRepository.countSearch(projectId);
    return PageResponse.of(rows.stream().map(GovernanceService::toCrResponse).toList(), page, total);
  }

  @Transactional
  public ChangeRequestResponse changeRequestStatus(UUID id, EntityStatusUpdateRequest req, AuthPrincipal p) {
    StandardRows.ChangeRequestRow row = changeRequestRepository.findById(id)
        .orElseThrow(() -> ApiExceptions.notFound("change_request", id));
    accessResolver.requireProject(p, row.projectId());
    writeGuard.assertWritable(row.projectId());
    ChangeRequestStatus next = parseCr(req.status());
    if (!row.status().canTransitionTo(next)) {
      throw ApiExceptions.invalidTransition(row.status(), next);
    }
    Instant now = Instant.now(clock);
    if (next == ChangeRequestStatus.APPLIED) {
      changeRequestRepository.markApplied(id, now);
    } else {
      changeRequestRepository.updateStatus(id, next, p.userId(), now);
    }
    historyRecorder.record(HistoryEntityType.CHANGE_REQUEST, id, row.projectId(),
        "status", row.status().name(), next.name(), RequirementService.actorOf(p));
    return toCrResponse(changeRequestRepository.findById(id).orElse(row));
  }

  @Transactional(readOnly = true)
  public PageResponse<CorrectionActionResponse> listCorrections(UUID projectId, CorrectionStatus status,
      PageQuery page, AuthPrincipal p) {
    accessResolver.requireProject(p, projectId);
    var sort = CorrectionActionRepository.sort(page.sort());
    var rows = correctionActionRepository.search(projectId, status, sort, page);
    long total = correctionActionRepository.countSearch(projectId, status);
    return PageResponse.of(rows.stream().map(r -> toCorrectionResponse(r, clock)).toList(), page, total);
  }

  @Transactional
  public CorrectionActionResponse changeCorrectionStatus(UUID id, EntityStatusUpdateRequest req, AuthPrincipal p) {
    StandardRows.CorrectionActionRow row = correctionActionRepository.findById(id)
        .orElseThrow(() -> ApiExceptions.notFound("correction_action", id));
    accessResolver.requireProject(p, row.projectId());
    writeGuard.assertWritable(row.projectId());
    CorrectionStatus next = parseCorrection(req.status());
    if (!row.status().canTransitionTo(next)) {
      throw ApiExceptions.invalidTransition(row.status(), next);
    }
    Instant now = Instant.now(clock);
    correctionActionRepository.updateStatus(id, next, now);
    historyRecorder.record(HistoryEntityType.CORRECTION_ACTION, id, row.projectId(),
        "status", row.status().name(), next.name(), RequirementService.actorOf(p));
    return toCorrectionResponse(correctionActionRepository.findById(id).orElse(row), clock);
  }

  @Transactional(readOnly = true)
  public PageResponse<ProgressRecordResponse> listProgress(UUID projectId, PageQuery page, AuthPrincipal p) {
    accessResolver.requireProject(p, projectId);
    var sort = GovernanceRepository.progressSort(page.sort());
    var rows = governanceRepository.searchProgress(projectId, sort, page);
    long total = governanceRepository.countProgress(projectId);
    return PageResponse.of(rows.stream().map(GovernanceService::toProgressResponse).toList(), page, total);
  }

  @Transactional(readOnly = true)
  public AcceptanceRecordResponse findAcceptance(UUID projectId, AuthPrincipal p) {
    accessResolver.requireProject(p, projectId);
    return governanceRepository.findIssued(projectId)
        .map(r -> toAcceptanceResponse(r, userName(r.acceptedByUserId())))
        .orElse(null);
  }

  @Transactional
  public AcceptanceRecordResponse createAcceptance(UUID projectId, AcceptanceRecordCreateRequest req,
      AuthPrincipal p) {
    accessResolver.requireProject(p, projectId);
    writeGuard.assertWritable(projectId);
    if (governanceRepository.findIssued(projectId).isPresent()) {
      throw ApiExceptions.duplicate("acceptance_record", "project:" + projectId);
    }
    Instant acceptedAt = req.acceptedAt() == null ? Instant.now(clock)
        : req.acceptedAt().atStartOfDay(ZoneId.of("UTC")).toInstant();
    UUID acceptedBy = resolveUserId(req.acceptedBy());
    UUID id = governanceRepository.insertAcceptance(projectId, acceptedBy, acceptedAt,
        req.conditions(), req.documentId());
    historyRecorder.record(HistoryEntityType.ACCEPTANCE_RECORD, id, projectId,
        "status", null, AcceptanceStatus.ISSUED.name(), RequirementService.actorOf(p));
    StandardRows.AcceptanceRow saved = governanceRepository.findAcceptanceById(id).orElseThrow();
    return toAcceptanceResponse(saved, userName(saved.acceptedByUserId()));
  }

  private String userName(UUID userId) {
    if (userId == null) {
      return null;
    }
    return jdbc.sql("select name from app_user where id = :id").param("id", userId)
        .query(String.class).optional().orElse(null);
  }

  private UUID resolveUserId(String nameOrId) {
    if (nameOrId == null || nameOrId.isBlank()) {
      return null;
    }
    return jdbc.sql("select id from app_user where lower(name) = lower(:n) or lower(email) = lower(:n)")
        .param("n", nameOrId).query(UUID.class).optional()
        .orElseThrow(() -> ApiExceptions.validationFailed("수락자를 찾을 수 없습니다: " + nameOrId));
  }

  private static ChangeRequestStatus parseCr(String s) {
    try { return ChangeRequestStatus.valueOf(s); }
    catch (Exception e) { throw ApiExceptions.validationFailed("알 수 없는 상태: " + s); }
  }

  private static CorrectionStatus parseCorrection(String s) {
    try { return CorrectionStatus.valueOf(s); }
    catch (Exception e) { throw ApiExceptions.validationFailed("알 수 없는 상태: " + s); }
  }

  static ChangeRequestResponse toCrResponse(StandardRows.ChangeRequestRow r) {
    return new ChangeRequestResponse(r.id(), r.projectId(), r.code(), r.title(), r.reason(),
        r.impactSummary(), r.status(), new SourceRef("MANUAL", null, null, null), r.updatedAt());
  }

  static CorrectionActionResponse toCorrectionResponse(StandardRows.CorrectionActionRow r, Clock clock) {
    long overdueDays = 0;
    if (r.status() != CorrectionStatus.DONE && r.dueDate() != null) {
      LocalDate today = LocalDate.now(clock);
      if (r.dueDate().isBefore(today)) {
        overdueDays = today.toEpochDay() - r.dueDate().toEpochDay();
      }
    }
    return new CorrectionActionResponse(r.id(), r.projectId(), r.code(), r.finding(), r.action(),
        r.owner(), r.dueDate(), r.status(), overdueDays, r.updatedAt());
  }

  static ProgressRecordResponse toProgressResponse(StandardRows.ProgressRecordRow r) {
    String period = r.periodStart().getYear() + "-" + String.format("%02d", r.periodStart().getMonthValue());
    return new ProgressRecordResponse(r.id(), r.projectId(), period, r.plannedPct(), r.actualPct(),
        r.summary(), new SourceRef(r.sourceKind(), r.toolConnectionId(), r.externalId(), r.externalUrl()));
  }

  static AcceptanceRecordResponse toAcceptanceResponse(StandardRows.AcceptanceRow r, String acceptedByName) {
    String documentUri = null;
    if (r.workProductId() != null) {
      documentUri = "/api/work-products/" + r.workProductId();
    }
    LocalDate acceptedDate = r.acceptedAt() == null ? null
        : r.acceptedAt().atZone(java.time.ZoneOffset.UTC).toLocalDate();
    return new AcceptanceRecordResponse(r.id(), r.projectId(), acceptedByName, acceptedDate, r.conditions(),
        documentUri, r.status(), r.createdAt());
  }
}
