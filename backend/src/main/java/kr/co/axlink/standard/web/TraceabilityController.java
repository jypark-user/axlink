package kr.co.axlink.standard.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.domain.TraceLinkKind;
import kr.co.axlink.standard.service.TraceLinkService;
import kr.co.axlink.standard.service.TraceabilityService;
import kr.co.axlink.standard.web.StandardDtos.TraceLinkCreateRequest;
import kr.co.axlink.standard.web.StandardDtos.TraceLinkResponse;
import kr.co.axlink.standard.web.StandardDtos.TraceabilityRowResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TraceabilityController {

  private final TraceLinkService traceLinkService;
  private final TraceabilityService traceabilityService;

  public TraceabilityController(TraceLinkService traceLinkService, TraceabilityService traceabilityService) {
    this.traceLinkService = traceLinkService;
    this.traceabilityService = traceabilityService;
  }

  @GetMapping("/api/projects/{projectId}/traceability")
  public PageResponse<TraceabilityRowResponse> rows(@PathVariable UUID projectId, PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return traceabilityService.rows(projectId, page, principal);
  }

  @GetMapping("/api/projects/{projectId}/trace-links")
  public PageResponse<TraceLinkResponse> listLinks(@PathVariable UUID projectId,
      @RequestParam(required = false) TraceEntityType fromType,
      @RequestParam(required = false) TraceLinkKind linkKind,
      PageQuery page, @AuthenticationPrincipal AuthPrincipal principal) {
    return traceLinkService.list(projectId, fromType, linkKind, page, principal);
  }

  @PostMapping("/api/projects/{projectId}/trace-links")
  public ResponseEntity<TraceLinkResponse> createLink(@PathVariable UUID projectId,
      @RequestBody TraceLinkCreateRequest req, @AuthenticationPrincipal AuthPrincipal principal) {
    return ResponseEntity.status(201).body(traceLinkService.createManual(projectId, req, principal));
  }

  @DeleteMapping("/api/trace-links/{traceLinkId}")
  public ResponseEntity<Void> deleteLink(@PathVariable UUID traceLinkId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    traceLinkService.delete(traceLinkId, principal);
    return ResponseEntity.noContent().build();
  }
}
