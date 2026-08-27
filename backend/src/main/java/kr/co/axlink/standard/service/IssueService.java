package kr.co.axlink.standard.service;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.IssueSeverity;
import kr.co.axlink.standard.domain.IssueStatus;
import kr.co.axlink.standard.repository.IssueRepository;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.web.StandardDtos.IssueResponse;
import kr.co.axlink.standard.web.StandardDtos.SourceRef;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IssueService {

  private final IssueRepository issueRepository;
  private final ProjectAccessResolver accessResolver;

  public IssueService(IssueRepository issueRepository, ProjectAccessResolver accessResolver) {
    this.issueRepository = issueRepository;
    this.accessResolver = accessResolver;
  }

  @Transactional(readOnly = true)
  public PageResponse<IssueResponse> list(UUID projectId, IssueStatus status, IssueSeverity severity,
      String assignee, String q, PageQuery page, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    var sort = IssueRepository.sort(page.sort());
    var rows = issueRepository.search(projectId, status, severity, assignee, q, sort, page);
    long total = issueRepository.countSearch(projectId, status, severity, assignee, q);
    return PageResponse.of(rows.stream().map(IssueService::toResponse).toList(), page, total);
  }

  @Transactional(readOnly = true)
  public IssueResponse get(UUID issueId, AuthPrincipal principal) {
    StandardRows.IssueRow row = issueRepository.findById(issueId)
        .orElseThrow(() -> ApiExceptions.notFound("issue", issueId));
    accessResolver.requireProject(principal, row.projectId());
    return toResponse(row);
  }

  static SourceRef toSourceRef(StandardRows.IssueRow r) {
    return new SourceRef(r.sourceKind(), r.toolConnectionId(), r.externalId(), r.externalUrl());
  }

  static IssueResponse toResponse(StandardRows.IssueRow r) {
    return new IssueResponse(r.id(), r.projectId(), r.issueKey(), r.title(), r.status(),
        r.severity(), r.assignee(), r.resolvedAt(), toSourceRef(r), r.updatedAt());
  }
}
