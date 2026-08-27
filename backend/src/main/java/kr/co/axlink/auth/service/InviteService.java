package kr.co.axlink.auth.service;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.auth.web.AuthDtos.LoginResponse;
import kr.co.axlink.auth.web.InviteDtos.AcceptRequest;
import kr.co.axlink.auth.web.InviteDtos.InviteKind;
import kr.co.axlink.auth.web.InviteDtos.InviteResponse;
import kr.co.axlink.auth.web.InviteDtos.PreviewResponse;
import kr.co.axlink.auth.web.InviteDtos.UserInviteLinkResponse;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.support.Hashes;
import kr.co.axlink.org.domain.AppUser;
import kr.co.axlink.org.domain.OrgStatus;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Organization;
import kr.co.axlink.org.domain.Role;
import kr.co.axlink.org.domain.UserInvitation;
import kr.co.axlink.org.domain.UserStatus;
import kr.co.axlink.org.repository.AppUserRepository;
import kr.co.axlink.org.repository.OrganizationRepository;
import kr.co.axlink.org.repository.UserInvitationRepository;
import kr.co.axlink.project.domain.AssignmentStatus;
import kr.co.axlink.project.domain.Project;
import kr.co.axlink.project.domain.ProjectAssignment;
import kr.co.axlink.project.domain.ProjectInvite;
import kr.co.axlink.project.repository.ProjectAssignmentRepository;
import kr.co.axlink.project.repository.ProjectInviteRepository;
import kr.co.axlink.project.repository.ProjectRepository;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 초대는 두 가지다. 어느 쪽이든 발송하지 않고 링크만 만들어 준다.
 * PROJECT — 발주사가 만든 링크로 용역사가 직접 계정을 만들고 그 프로젝트에 할당된다.
 * USER — 관리자가 만들어 둔 계정의 비밀번호를 본인이 정한다.
 */
@Service
public class InviteService {

  private static final SecureRandom RANDOM = new SecureRandom();
  private static final Duration TTL = Duration.ofDays(14);
  /**
   * 용역사 권한은 나누지 않는다 — 일을 하려면 레포 연결과 문서 업로드가 있어야 하고,
   * 발주사용 대시보드는 보지 않는다.
   */

  private final ProjectInviteRepository inviteRepository;
  private final UserInvitationRepository userInvitationRepository;
  private final ProjectAssignmentRepository assignmentRepository;
  private final ProjectRepository projectRepository;
  private final OrganizationRepository organizationRepository;
  private final AppUserRepository appUserRepository;
  private final ProjectAccessResolver accessResolver;
  private final PasswordEncoder passwordEncoder;
  private final AuthService authService;
  private final Clock clock;

  public InviteService(ProjectInviteRepository inviteRepository,
      UserInvitationRepository userInvitationRepository,
      ProjectAssignmentRepository assignmentRepository, ProjectRepository projectRepository,
      OrganizationRepository organizationRepository, AppUserRepository appUserRepository,
      ProjectAccessResolver accessResolver, PasswordEncoder passwordEncoder,
      AuthService authService, Clock clock) {
    this.inviteRepository = inviteRepository;
    this.userInvitationRepository = userInvitationRepository;
    this.assignmentRepository = assignmentRepository;
    this.projectRepository = projectRepository;
    this.organizationRepository = organizationRepository;
    this.appUserRepository = appUserRepository;
    this.accessResolver = accessResolver;
    this.passwordEncoder = passwordEncoder;
    this.authService = authService;
    this.clock = clock;
  }

  // ---------- PROJECT 초대 (발주사 → 용역사) ----------

  @Transactional
  public InviteResponse create(UUID projectId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    String token = newToken();
    ProjectInvite invite = new ProjectInvite(null, projectId, Hashes.sha256Hex(token),
        clock.instant().plus(TTL), null, principal.userId(), null);
    UUID id = inviteRepository.insert(invite);
    return toResponse(inviteRepository.findById(id).orElseThrow(), token);
  }

  @Transactional
  public void revoke(UUID projectId, UUID inviteId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    ProjectInvite invite = inviteRepository.findById(inviteId)
        .orElseThrow(() -> ApiExceptions.notFound("project_invite", inviteId));
    if (!invite.projectId().equals(projectId)) {
      throw ApiExceptions.notFound("project_invite", inviteId);
    }
    inviteRepository.revoke(inviteId, clock.instant());
  }

  // ---------- USER 초대 (관리자 → 계정 본인) ----------

  /** 이전에 발급한 링크는 무효가 된다. */
  @Transactional
  public UserInviteLinkResponse createUserInviteLink(UUID userId, AuthPrincipal principal) {
    AppUser user = appUserRepository.findById(userId)
        .orElseThrow(() -> ApiExceptions.notFound("app_user", userId));
    if (user.status() != UserStatus.INVITED) {
      throw ApiExceptions.invalidTransition(user.status(), UserStatus.INVITED);
    }
    Instant now = clock.instant();
    userInvitationRepository.expireOpen(userId, now);
    String token = newToken();
    Instant expiresAt = now.plus(TTL);
    userInvitationRepository.insert(userId, Hashes.sha256Hex(token), expiresAt,
        principal.userId());
    return new UserInviteLinkResponse(token, expiresAt);
  }

  // ---------- 링크를 받은 쪽 (인증 없이 열린다) ----------

  @Transactional(readOnly = true)
  public PreviewResponse preview(String token) {
    String hash = Hashes.sha256Hex(token);
    Instant now = clock.instant();

    ProjectInvite projectInvite = inviteRepository.findByTokenHash(hash)
        .filter(i -> i.usable(now)).orElse(null);
    if (projectInvite != null) {
      Project project = projectRepository.findById(projectInvite.projectId())
          .orElseThrow(ApiExceptions::tokenInvalid);
      return new PreviewResponse(InviteKind.PROJECT, project.name(), null, null, null,
          projectInvite.expiresAt());
    }

    UserInvitation userInvite = usableUserInvitation(hash, now);
    AppUser user = appUserRepository.findById(userInvite.appUserId())
        .orElseThrow(ApiExceptions::tokenInvalid);
    return new PreviewResponse(InviteKind.USER, null, orgName(user.organizationId()), user.email(),
        user.name(), userInvite.expiresAt());
  }

  @Transactional
  public LoginResponse accept(AcceptRequest req, String userAgent) {
    validatePassword(req.password());
    String hash = Hashes.sha256Hex(req.token());
    Instant now = clock.instant();

    ProjectInvite projectInvite = inviteRepository.findByTokenHash(hash)
        .filter(i -> i.usable(now)).orElse(null);
    UUID userId = projectInvite != null
        ? registerContractor(projectInvite, req)
        : activateInvitedUser(usableUserInvitation(hash, now), req, now);
    return authService.issueSession(appUserRepository.findById(userId).orElseThrow(), userAgent);
  }

  /** 링크를 받은 용역사가 회사·본인 정보를 적어 계정을 만들고, 그 계정이 프로젝트에 할당된다. */
  private UUID registerContractor(ProjectInvite invite, AcceptRequest req) {
    if (isBlank(req.contractorOrgName()) || isBlank(req.email()) || isBlank(req.name())) {
      throw ApiExceptions.validationFailed("회사명과 이름, 이메일을 입력해야 합니다.");
    }
    String email = req.email().trim();
    if (appUserRepository.findByEmailIgnoreCase(email).isPresent()) {
      throw ApiExceptions.duplicate("app_user", email);
    }
    Organization contractor = contractorOrgByName(req.contractorOrgName().trim());
    UUID userId = appUserRepository.insert(new AppUser(null, contractor.id(), email,
        req.name().trim(), passwordEncoder.encode(req.password()), Role.CONTRACTOR,
        UserStatus.ACTIVE, null, null, null));
    assignmentRepository.insert(new ProjectAssignment(null, invite.projectId(), contractor.id(),
        userId, AssignmentStatus.ACTIVE, invite.createdByUserId(), null, null, null));
    return userId;
  }

  private static boolean isBlank(String value) {
    return value == null || value.isBlank();
  }

  /** 관리자가 만들어 둔 계정의 비밀번호를 본인이 정한다. */
  private UUID activateInvitedUser(UserInvitation invite, AcceptRequest req, Instant now) {
    AppUser user = appUserRepository.findById(invite.appUserId())
        .orElseThrow(ApiExceptions::tokenInvalid);
    if (user.status() != UserStatus.INVITED) {
      throw ApiExceptions.invalidTransition(user.status(), UserStatus.ACTIVE);
    }
    appUserRepository.updatePasswordHash(user.id(), passwordEncoder.encode(req.password()));
    appUserRepository.updateProfile(user.id(), null, null, UserStatus.ACTIVE);
    userInvitationRepository.markAccepted(invite.id(), now);
    return user.id();
  }

  private UserInvitation usableUserInvitation(String tokenHash, Instant now) {
    return userInvitationRepository.findByTokenHash(tokenHash)
        .filter(i -> i.usable(now))
        .orElseThrow(ApiExceptions::tokenInvalid);
  }

  private String newToken() {
    byte[] raw = new byte[32];
    RANDOM.nextBytes(raw);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
  }

  private void validatePassword(String password) {
    if (password.length() < 8 || !password.matches(".*[A-Za-z].*")
        || !password.matches(".*\\d.*")) {
      throw ApiExceptions.validationFailed("비밀번호는 영문과 숫자를 포함해 8자 이상이어야 합니다.");
    }
  }

  private Organization contractorOrgByName(String name) {
    Organization existing = organizationRepository.findByNameIgnoreCase(name).orElse(null);
    if (existing == null) {
      UUID id = organizationRepository.insert(
          new Organization(null, name, OrgType.CONTRACTOR, null, OrgStatus.ACTIVE, null, null));
      return organizationRepository.findById(id).orElseThrow();
    }
    if (existing.type() != OrgType.CONTRACTOR) {
      throw ApiExceptions.validationFailed("같은 이름의 발주사 조직이 이미 있습니다.");
    }
    return existing;
  }

  private String orgName(UUID organizationId) {
    return organizationRepository.findById(organizationId).map(Organization::name).orElse("");
  }

  private InviteResponse toResponse(ProjectInvite i, String token) {
    return new InviteResponse(i.id(), i.projectId(), i.expiresAt(), i.revokedAt(), i.createdAt(),
        token);
  }
}
