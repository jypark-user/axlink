package kr.co.axlink.dashboard.web;

import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.dashboard.dto.DashboardCreateRequest;
import kr.co.axlink.dashboard.dto.DashboardDetailResponse;
import kr.co.axlink.dashboard.dto.DashboardLayoutUpdateRequest;
import kr.co.axlink.dashboard.dto.DashboardSummaryResponse;
import kr.co.axlink.dashboard.dto.DashboardUpdateRequest;
import kr.co.axlink.dashboard.service.DashboardService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/dashboards")
public class DashboardController {

  private final DashboardService dashboardService;

  public DashboardController(DashboardService dashboardService) {
    this.dashboardService = dashboardService;
  }

  @GetMapping
  public List<DashboardSummaryResponse> list(@RequestParam(required = false) UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return dashboardService.list(projectId, principal);
  }

  @PostMapping
  public ResponseEntity<DashboardDetailResponse> create(@Valid @RequestBody DashboardCreateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    DashboardDetailResponse body = dashboardService.create(req, principal);
    return ResponseEntity.status(HttpStatus.CREATED).body(body);
  }

  @GetMapping("/{dashboardId}")
  public DashboardDetailResponse get(@PathVariable UUID dashboardId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return dashboardService.get(dashboardId, principal);
  }

  @PatchMapping("/{dashboardId}")
  public DashboardDetailResponse update(@PathVariable UUID dashboardId,
      @Valid @RequestBody DashboardUpdateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return dashboardService.update(dashboardId, req, principal);
  }

  @DeleteMapping("/{dashboardId}")
  public ResponseEntity<Void> delete(@PathVariable UUID dashboardId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    dashboardService.delete(dashboardId, principal);
    return ResponseEntity.noContent().build();
  }

  @PutMapping("/{dashboardId}/layout")
  public DashboardDetailResponse replaceLayout(@PathVariable UUID dashboardId,
      @Valid @RequestBody DashboardLayoutUpdateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return dashboardService.replaceLayout(dashboardId, req, principal);
  }
}
