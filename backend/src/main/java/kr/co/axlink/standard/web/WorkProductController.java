package kr.co.axlink.standard.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.standard.service.WorkProductService;
import kr.co.axlink.standard.web.StandardDtos.WorkProductChecklistResponse;
import kr.co.axlink.standard.web.StandardDtos.WorkProductDetailResponse;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkProductController {

  private final WorkProductService workProductService;

  public WorkProductController(WorkProductService workProductService) {
    this.workProductService = workProductService;
  }

  @GetMapping("/api/projects/{projectId}/work-products")
  public WorkProductChecklistResponse checklist(@PathVariable UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return workProductService.checklist(projectId, principal);
  }

  @GetMapping("/api/work-products/{workProductId}")
  public WorkProductDetailResponse get(@PathVariable UUID workProductId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return workProductService.get(workProductId, principal);
  }
}
