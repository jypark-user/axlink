package kr.co.axlink.standard.service;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.RiskLevel;
import kr.co.axlink.standard.domain.RiskStatus;
import kr.co.axlink.standard.repository.RiskRepository;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.web.StandardDtos.RiskResponse;
import kr.co.axlink.standard.web.StandardDtos.SourceRef;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RiskService {

  private final RiskRepository riskRepository;
  private final ProjectAccessResolver accessResolver;

  public RiskService(RiskRepository riskRepository, ProjectAccessResolver accessResolver) {
    this.riskRepository = riskRepository;
    this.accessResolver = accessResolver;
  }

  @Transactional(readOnly = true)
  public PageResponse<RiskResponse> list(UUID projectId, RiskStatus status, RiskLevel severity,
      PageQuery page, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    var sort = RiskRepository.sort(page.sort());
    var rows = riskRepository.search(projectId, status, severity, sort, page);
    long total = riskRepository.countSearch(projectId, status, severity);
    return PageResponse.of(rows.stream().map(RiskService::toResponse).toList(), page, total);
  }

  static SourceRef toSourceRef(StandardRows.RiskRow r) {
    return new SourceRef(r.sourceKind(), r.toolConnectionId(), r.externalId(), r.externalUrl());
  }

  static RiskResponse toResponse(StandardRows.RiskRow r) {
    return new RiskResponse(r.id(), r.projectId(), r.title(), r.probability(), r.impact(),
        r.severity(), r.mitigation(), r.status(), toSourceRef(r), r.updatedAt());
  }
}
