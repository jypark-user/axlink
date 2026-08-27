package kr.co.axlink.standard.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.CorrectionStatus;
import kr.co.axlink.standard.service.GovernanceService;
import kr.co.axlink.standard.web.StandardDtos.AcceptanceRecordCreateRequest;
import kr.co.axlink.standard.web.StandardDtos.AcceptanceRecordResponse;
import kr.co.axlink.standard.web.StandardDtos.ChangeRequestResponse;
import kr.co.axlink.standard.web.StandardDtos.CorrectionActionResponse;
import kr.co.axlink.standard.web.StandardDtos.EntityStatusUpdateRequest;
import kr.co.axlink.standard.web.StandardDtos.ProgressRecordResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GovernanceController {

  private final GovernanceService governanceService;

  public GovernanceController(GovernanceService governanceService) {
    this.governanceService = governanceService;
  }

  @GetMapping("/api/projects/{projectId}/change-requests")
  public PageResponse<ChangeRequestResponse> listChangeRequests(@PathVariable UUID projectId,
      PageQuery page, @AuthenticationPrincipal AuthPrincipal principal) {
    return governanceService.listChangeRequests(projectId, page, principal);
  }

  @PatchMapping("/api/change-requests/{changeRequestId}/status")
  public ChangeRequestResponse changeRequestStatus(@PathVariable UUID changeRequestId,
      @RequestBody EntityStatusUpdateRequest req, @AuthenticationPrincipal AuthPrincipal principal) {
    return governanceService.changeRequestStatus(changeRequestId, req, principal);
  }

  @GetMapping("/api/projects/{projectId}/correction-actions")
  public PageResponse<CorrectionActionResponse> listCorrections(@PathVariable UUID projectId,
      @RequestParam(required = false) CorrectionStatus status, PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return governanceService.listCorrections(projectId, status, page, principal);
  }

  @PatchMapping("/api/correction-actions/{correctionActionId}/status")
  public CorrectionActionResponse changeCorrectionStatus(@PathVariable UUID correctionActionId,
      @RequestBody EntityStatusUpdateRequest req, @AuthenticationPrincipal AuthPrincipal principal) {
    return governanceService.changeCorrectionStatus(correctionActionId, req, principal);
  }

  @GetMapping("/api/projects/{projectId}/progress-records")
  public PageResponse<ProgressRecordResponse> listProgress(@PathVariable UUID projectId,
      PageQuery page, @AuthenticationPrincipal AuthPrincipal principal) {
    return governanceService.listProgress(projectId, page, principal);
  }

  @GetMapping("/api/projects/{projectId}/acceptance-record")
  public ResponseEntity<AcceptanceRecordResponse> findAcceptance(@PathVariable UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    AcceptanceRecordResponse r = governanceService.findAcceptance(projectId, principal);
    return r == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(r);
  }

  @PostMapping("/api/projects/{projectId}/acceptance-record")
  public AcceptanceRecordResponse createAcceptance(@PathVariable UUID projectId,
      @RequestBody AcceptanceRecordCreateRequest req, @AuthenticationPrincipal AuthPrincipal principal) {
    return governanceService.createAcceptance(projectId, req, principal);
  }
}
