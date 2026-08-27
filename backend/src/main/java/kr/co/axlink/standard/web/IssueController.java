package kr.co.axlink.standard.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.IssueSeverity;
import kr.co.axlink.standard.domain.IssueStatus;
import kr.co.axlink.standard.service.IssueService;
import kr.co.axlink.standard.web.StandardDtos.IssueResponse;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IssueController {

  private final IssueService issueService;

  public IssueController(IssueService issueService) {
    this.issueService = issueService;
  }

  @GetMapping("/api/projects/{projectId}/issues")
  public PageResponse<IssueResponse> list(@PathVariable UUID projectId,
      @RequestParam(required = false) IssueStatus status,
      @RequestParam(required = false) IssueSeverity severity,
      @RequestParam(required = false) String assignee,
      @RequestParam(required = false) String q,
      PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return issueService.list(projectId, status, severity, assignee, q, page, principal);
  }

  @GetMapping("/api/issues/{issueId}")
  public IssueResponse get(@PathVariable UUID issueId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return issueService.get(issueId, principal);
  }
}
