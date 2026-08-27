package kr.co.axlink.project.service;

import java.time.Clock;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.org.domain.AppUser;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Organization;
import kr.co.axlink.org.repository.AppUserRepository;
import kr.co.axlink.org.repository.OrganizationRepository;
import kr.co.axlink.project.domain.AssignmentStatus;
import kr.co.axlink.project.domain.ProjectAssignment;
import kr.co.axlink.project.repository.ProjectAssignmentRepository;
import kr.co.axlink.project.web.AssignmentCreateRequest;
import kr.co.axlink.project.web.AssignmentResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AssignmentService {

  private final ProjectAssignmentRepository assignmentRepository;
  private final AppUserRepository appUserRepository;
  private final OrganizationRepository organizationRepository;
  private final ProjectAccessResolver accessResolver;
  private final Clock clock;

  public AssignmentService(ProjectAssignmentRepository assignmentRepository,
      AppUserRepository appUserRepository, OrganizationRepository organizationRepository,
      ProjectAccessResolver accessResolver, Clock clock) {
    this.assignmentRepository = assignmentRepository;
    this.appUserRepository = appUserRepository;
    this.organizationRepository = organizationRepository;
    this.accessResolver = accessResolver;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public List<AssignmentResponse> list(UUID projectId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    return toResponses(assignmentRepository.findByProjectId(projectId));
  }

  @Transactional
  public List<AssignmentResponse> assign(UUID projectId, AssignmentCreateRequest req,
      AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    Organization contractor = organizationRepository.findById(req.contractorOrgId())
        .orElseThrow(() -> ApiExceptions.notFound("organization", req.contractorOrgId()));
    if (contractor.type() != OrgType.CONTRACTOR) {
      throw ApiExceptions.validationFailed("용역사 조직에만 할당할 수 있습니다.");
    }
    List<ProjectAssignment> created = new ArrayList<>();
    for (UUID userId : req.userIds()) {
      AppUser user = appUserRepository.findById(userId)
          .orElseThrow(() -> ApiExceptions.notFound("app_user", userId));
      if (!user.organizationId().equals(req.contractorOrgId())) {
        throw ApiExceptions.validationFailed("사용자가 해당 용역사 조직에 속하지 않습니다.");
      }
      if (assignmentRepository.existsActive(projectId, userId)) {
        throw ApiExceptions.duplicate("project_assignment", projectId + "/" + userId);
      }
      ProjectAssignment a = new ProjectAssignment(null, projectId, req.contractorOrgId(), userId,
          AssignmentStatus.ACTIVE, principal.userId(), null, null, null);
      UUID id = assignmentRepository.insert(a);
      created.add(assignmentRepository.findById(id).orElseThrow());
    }
    return toResponses(created);
  }

  @Transactional
  public void revoke(UUID projectId, UUID assignmentId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    ProjectAssignment a = findAssignment(assignmentId, projectId);
    if (a.status() != AssignmentStatus.ACTIVE) {
      throw ApiExceptions.invalidTransition(a.status(), AssignmentStatus.REVOKED);
    }
    assignmentRepository.revoke(assignmentId, clock.instant());
  }

  private ProjectAssignment findAssignment(UUID assignmentId, UUID projectId) {
    ProjectAssignment a = assignmentRepository.findById(assignmentId)
        .orElseThrow(() -> ApiExceptions.notFound("project_assignment", assignmentId));
    if (!a.projectId().equals(projectId)) {
      throw ApiExceptions.notFound("project_assignment", assignmentId);
    }
    return a;
  }

  private List<AssignmentResponse> toResponses(List<ProjectAssignment> rows) {
    Map<UUID, String> orgNames = new HashMap<>();
    Map<UUID, String> userNames = new HashMap<>();
    Map<UUID, String> userEmails = new HashMap<>();
    for (ProjectAssignment a : rows) {
      orgNames.computeIfAbsent(a.contractorOrgId(),
          id -> organizationRepository.findById(id).map(Organization::name).orElse(""));
      userNames.computeIfAbsent(a.userId(),
          id -> appUserRepository.findById(id).map(AppUser::name).orElse(""));
      userEmails.computeIfAbsent(a.userId(),
          id -> appUserRepository.findById(id).map(AppUser::email).orElse(""));
    }
    return rows.stream()
        .map(a -> new AssignmentResponse(a.id(), a.projectId(), a.contractorOrgId(),
            orgNames.getOrDefault(a.contractorOrgId(), ""),
            a.userId(), userNames.getOrDefault(a.userId(), ""),
            userEmails.getOrDefault(a.userId(), ""),
            a.status().name(), a.createdAt()))
        .toList();
  }
}
