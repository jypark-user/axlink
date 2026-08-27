package kr.co.axlink.dashboard.web;

import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.dashboard.dto.DashboardPresetResponse;
import kr.co.axlink.dashboard.dto.DashboardPresetSaveRequest;
import kr.co.axlink.dashboard.dto.WidgetCreateRequest;
import kr.co.axlink.dashboard.service.DashboardPresetService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 꾸민 대시보드 구성을 이름 붙여 두고 다시 쓰는 자리. 조직 안에서만 보인다. */
@RestController
@RequestMapping("/api/dashboard-presets")
public class DashboardPresetController {

  private final DashboardPresetService presetService;

  public DashboardPresetController(DashboardPresetService presetService) {
    this.presetService = presetService;
  }

  @GetMapping
  public List<DashboardPresetResponse> list(@AuthenticationPrincipal AuthPrincipal principal) {
    return presetService.list(principal);
  }

  /** 프리셋에 담긴 위젯 명세와 자리 — 배치는 화면이 사업 범위를 채워 넣어 만든다. */
  @GetMapping("/{presetId}/items")
  public List<WidgetCreateRequest> items(@PathVariable UUID presetId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return presetService.items(presetId, principal);
  }

  @PostMapping
  public ResponseEntity<DashboardPresetResponse> save(
      @Valid @RequestBody DashboardPresetSaveRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return ResponseEntity.status(HttpStatus.CREATED).body(presetService.save(req, principal));
  }

  @DeleteMapping("/{presetId}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void delete(@PathVariable UUID presetId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    presetService.delete(presetId, principal);
  }
}
