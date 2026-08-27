package kr.co.axlink.org.service;

import java.util.List;
import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Organization;
import kr.co.axlink.org.repository.AppUserRepository;
import kr.co.axlink.org.repository.OrganizationRepository;
import kr.co.axlink.org.web.OrganizationCreateRequest;
import kr.co.axlink.org.web.OrganizationResponse;
import kr.co.axlink.org.web.OrganizationUpdateRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrganizationService {

  private final OrganizationRepository organizationRepository;
  private final AppUserRepository appUserRepository;
  private final CountQueries countQueries;

  public OrganizationService(OrganizationRepository organizationRepository,
      AppUserRepository appUserRepository, CountQueries countQueries) {
    this.organizationRepository = organizationRepository;
    this.appUserRepository = appUserRepository;
    this.countQueries = countQueries;
  }

  @Transactional(readOnly = true)
  public PageResponse<OrganizationResponse> list(OrgType type, String q, PageQuery page) {
    var sort = OrganizationRepository.sortSpec(page);
    List<Organization> rows = organizationRepository.search(type, q, sort, page);
    long total = organizationRepository.countSearch(type, q);
    List<OrganizationResponse> content = rows.stream().map(this::toResponse).toList();
    return PageResponse.of(content, page, total);
  }

  @Transactional
  public OrganizationResponse create(OrganizationCreateRequest req) {
    Organization org = new Organization(null, req.name(), req.type(), req.businessNo(), null, null, null);
    UUID id = organizationRepository.insert(org);
    return organizationRepository.findById(id)
        .map(this::toResponse)
        .orElseThrow(() -> ApiExceptions.internal("조직 생성 후 조회에 실패했습니다."));
  }

  @Transactional(readOnly = true)
  public OrganizationResponse get(UUID id) {
    return organizationRepository.findById(id)
        .map(this::toResponse)
        .orElseThrow(() -> ApiExceptions.notFound("organization", id));
  }

  @Transactional
  public OrganizationResponse update(UUID id, OrganizationUpdateRequest req) {
    Organization existing = organizationRepository.findById(id)
        .orElseThrow(() -> ApiExceptions.notFound("organization", id));
    String name = req.name() != null ? req.name() : existing.name();
    String businessNo = req.businessNo() != null ? req.businessNo() : existing.businessNo();
    organizationRepository.update(id, name, businessNo);
    return organizationRepository.findById(id)
        .map(this::toResponse)
        .orElseThrow(() -> ApiExceptions.internal("조직 수정 후 조회에 실패했습니다."));
  }

  private OrganizationResponse toResponse(Organization o) {
    return new OrganizationResponse(o.id(), o.name(), o.type(), o.businessNo(),
        countQueries.userCount(o.id()), countQueries.projectCount(o.id()), o.createdAt());
  }
}
