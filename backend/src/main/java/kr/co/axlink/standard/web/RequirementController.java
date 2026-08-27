package kr.co.axlink.standard.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.RequirementPriority;
import kr.co.axlink.standard.domain.RequirementStatus;
import kr.co.axlink.standard.service.RequirementService;
import kr.co.axlink.standard.web.StandardDtos.EntityStatusUpdateRequest;
import kr.co.axlink.standard.web.StandardDtos.RequirementDetailResponse;
import kr.co.axlink.standard.web.StandardDtos.RequirementResponse;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RequirementController {

  private final RequirementService requirementService;

  public RequirementController(RequirementService requirementService) {
    this.requirementService = requirementService;
  }

  @GetMapping("/api/projects/{projectId}/requirements")
  public PageResponse<RequirementResponse> list(@PathVariable UUID projectId,
      @RequestParam(required = false) RequirementStatus status,
      @RequestParam(required = false) RequirementPriority priority,
      @RequestParam(required = false) String q,
      PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return requirementService.list(projectId, status, priority, q, page, principal);
  }

  @GetMapping("/api/requirements/{requirementId}")
  public RequirementDetailResponse get(@PathVariable UUID requirementId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return requirementService.get(requirementId, principal);
  }

  @PatchMapping("/api/requirements/{requirementId}/status")
  public RequirementResponse changeStatus(@PathVariable UUID requirementId,
      @RequestBody EntityStatusUpdateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return requirementService.changeStatus(requirementId, req, principal);
  }
}
