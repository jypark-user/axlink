package kr.co.axlink.standard.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.RiskLevel;
import kr.co.axlink.standard.domain.RiskStatus;
import kr.co.axlink.standard.service.RiskService;
import kr.co.axlink.standard.web.StandardDtos.RiskResponse;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RiskController {

  private final RiskService riskService;

  public RiskController(RiskService riskService) {
    this.riskService = riskService;
  }

  @GetMapping("/api/projects/{projectId}/risks")
  public PageResponse<RiskResponse> list(@PathVariable UUID projectId,
      @RequestParam(required = false) RiskStatus status,
      @RequestParam(required = false) RiskLevel severity,
      PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return riskService.list(projectId, status, severity, page, principal);
  }
}
