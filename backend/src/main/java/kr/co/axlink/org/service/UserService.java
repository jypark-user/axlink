package kr.co.axlink.org.service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.org.domain.AppUser;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Organization;
import kr.co.axlink.org.domain.Role;
import kr.co.axlink.org.domain.UserStatus;
import kr.co.axlink.org.repository.AppUserRepository;
import kr.co.axlink.org.repository.OrganizationRepository;
import kr.co.axlink.org.web.UserCreateRequest;
import kr.co.axlink.org.web.UserResponse;
import kr.co.axlink.org.web.UserUpdateRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserService {

  private final AppUserRepository appUserRepository;
  private final OrganizationRepository organizationRepository;

  public UserService(AppUserRepository appUserRepository,
      OrganizationRepository organizationRepository) {
    this.appUserRepository = appUserRepository;
    this.organizationRepository = organizationRepository;
  }

  @Transactional(readOnly = true)
  public PageResponse<UserResponse> list(UUID organizationId, Role role, UserStatus status,
      String q, PageQuery page) {
    var sort = AppUserRepository.sortSpec(page);
    List<AppUser> rows = appUserRepository.search(organizationId, role, status, q, sort, page);
    long total = appUserRepository.countSearch(organizationId, role, status, q);
    Map<UUID, String> orgNames = organizationNamesOf(rows);
    List<UserResponse> content = rows.stream()
        .map(u -> toResponse(u, orgNames.getOrDefault(u.organizationId(), "")))
        .toList();
    return PageResponse.of(content, page, total);
  }

  @Transactional
  public UserResponse create(UserCreateRequest req) {
    Organization org = organizationRepository.findById(req.organizationId())
        .orElseThrow(() -> ApiExceptions.notFound("organization", req.organizationId()));
    validateRoleForOrgType(req.role(), org.type());
    if (appUserRepository.findByEmailIgnoreCase(req.email()).isPresent()) {
      throw ApiExceptions.duplicate("app_user", req.email());
    }
    AppUser user = new AppUser(null, req.organizationId(), req.email(), req.name(), null,
        req.role(), UserStatus.INVITED, null, null, null);
    UUID id = appUserRepository.insert(user);
    return appUserRepository.findById(id)
        .map(u -> toResponse(u, org.name()))
        .orElseThrow(() -> ApiExceptions.internal("계정 생성 후 조회에 실패했습니다."));
  }

  @Transactional(readOnly = true)
  public UserResponse get(UUID id) {
    AppUser u = appUserRepository.findById(id)
        .orElseThrow(() -> ApiExceptions.notFound("app_user", id));
    String orgName = organizationRepository.findById(u.organizationId())
        .map(Organization::name).orElse("");
    return toResponse(u, orgName);
  }

  @Transactional
  public UserResponse update(UUID id, UserUpdateRequest req) {
    AppUser existing = appUserRepository.findById(id)
        .orElseThrow(() -> ApiExceptions.notFound("app_user", id));
    if (req.role() != null) {
      Organization org = organizationRepository.findById(existing.organizationId())
          .orElseThrow(() -> ApiExceptions.notFound("organization", existing.organizationId()));
      validateRoleForOrgType(req.role(), org.type());
    }
    appUserRepository.updateProfile(id, req.name(), req.role(), req.status());
    return appUserRepository.findById(id)
        .map(u -> toResponse(u, organizationName(u.organizationId())))
        .orElseThrow(() -> ApiExceptions.internal("계정 수정 후 조회에 실패했습니다."));
  }

  private void validateRoleForOrgType(Role role, OrgType orgType) {
    if (role == Role.SUPER_ADMIN) {
      return;
    }
    if (role == Role.CLIENT && orgType != OrgType.CLIENT) {
      throw ApiExceptions.validationFailed("CLIENT 역할은 발주사 조직에만 지정할 수 있습니다.");
    }
    if (role == Role.CONTRACTOR && orgType != OrgType.CONTRACTOR) {
      throw ApiExceptions.validationFailed("CONTRACTOR 역할은 용역사 조직에만 지정할 수 있습니다.");
    }
  }

  private Map<UUID, String> organizationNamesOf(List<AppUser> users) {
    Map<UUID, String> names = new HashMap<>();
    for (AppUser u : users) {
      names.computeIfAbsent(u.organizationId(), this::organizationName);
    }
    return names;
  }

  private String organizationName(UUID organizationId) {
    return organizationRepository.findById(organizationId).map(Organization::name).orElse("");
  }

  private UserResponse toResponse(AppUser u, String organizationName) {
    return new UserResponse(u.id(), u.organizationId(), organizationName, u.email(), u.name(),
        u.role(), u.status(), u.lastLoginAt(), u.createdAt());
  }
}
