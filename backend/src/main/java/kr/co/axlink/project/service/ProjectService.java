package kr.co.axlink.project.service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.org.domain.Organization;
import kr.co.axlink.org.repository.OrganizationRepository;
import kr.co.axlink.project.domain.Project;
import kr.co.axlink.project.domain.ProjectStatus;
import kr.co.axlink.project.repository.ProjectAssignmentRepository;
import kr.co.axlink.project.repository.ProjectRepository;
import kr.co.axlink.project.web.ProjectCreateRequest;
import kr.co.axlink.project.web.ProjectDetailResponse;
import kr.co.axlink.project.web.ProjectMetrics;
import kr.co.axlink.project.web.ProjectSummaryResponse;
import kr.co.axlink.project.web.ProjectUpdateRequest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProjectService {

  static final String[][] WORK_PRODUCT_SEED = {
      {"STATEMENT_OF_WORK", "PM_1", null},
      {"PROJECT_PLAN", "PM_1", null},
      {"PROGRESS_STATUS_RECORD", "PM_2", null},
      {"MEETING_RECORD", "PM_2", null},
      {"CHANGE_REQUEST", "PM_2", null},
      {"CORRECTION_REGISTER", "PM_3", null},
      {"ACCEPTANCE_RECORD", "PM_4", null},
      {"PROJECT_REPOSITORY", "PM_1", null},
      {"REPOSITORY_BACKUP", "PM_2", null},
      {"VERIFICATION_RESULTS", "PM_3", null},
      {"VALIDATION_RESULTS", "PM_4", null},
      {"REQUIREMENTS_SPEC", null, "SI_2"},
      {"TRACEABILITY_RECORD", null, "SI_2"},
      {"SOFTWARE_DESIGN", null, "SI_3"},
      {"TEST_CASES_PROCEDURES", null, "SI_3"},
      {"SOFTWARE_COMPONENT", null, "SI_4"},
      {"SOFTWARE", null, "SI_5"},
      {"TEST_REPORT", null, "SI_5"},
      {"PRODUCT_OPERATION_GUIDE", null, "SI_5"},
      {"SOFTWARE_USER_DOC", null, "SI_5"},
      {"SOFTWARE_CONFIGURATION", null, "SI_6"},
      {"MAINTENANCE_DOC", null, "SI_6"}
  };

  private final ProjectRepository projectRepository;
  private final ProjectAssignmentRepository assignmentRepository;
  private final OrganizationRepository organizationRepository;
  private final ProjectAccessResolver accessResolver;
  private final ProjectMetricsReader metricsReader;
  private final PasswordEncoder passwordEncoder;
  private final JdbcClient jdbcClient;

  public ProjectService(ProjectRepository projectRepository,
      ProjectAssignmentRepository assignmentRepository,
      OrganizationRepository organizationRepository,
      ProjectAccessResolver accessResolver,
      ProjectMetricsReader metricsReader,
      PasswordEncoder passwordEncoder,
      JdbcClient jdbcClient) {
    this.projectRepository = projectRepository;
    this.assignmentRepository = assignmentRepository;
    this.organizationRepository = organizationRepository;
    this.accessResolver = accessResolver;
    this.metricsReader = metricsReader;
    this.passwordEncoder = passwordEncoder;
    this.jdbcClient = jdbcClient;
  }

  /**
   * 사업을 지운다. 등록할 때 정한 비밀번호를 맞춰야 한다 —
   * 사업과 함께 자료·요구사항·연동까지 사라지고 되돌릴 수 없다.
   */
  @Transactional
  public void delete(UUID projectId, String password, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    String hash = projectRepository.findDeletePasswordHash(projectId)
        .orElseThrow(() -> ApiExceptions.notFound("project", projectId));
    if (hash == null || hash.isBlank()) {
      throw ApiExceptions.validationFailed("삭제 비밀번호가 없는 사업입니다. 지울 수 없습니다.");
    }
    if (password == null || !passwordEncoder.matches(password, hash)) {
      throw ApiExceptions.validationFailed("삭제 비밀번호가 맞지 않습니다.");
    }
    projectRepository.delete(projectId);
  }

  @Transactional
  public ProjectDetailResponse create(ProjectCreateRequest req, AuthPrincipal principal) {
    if (req.startDate().isAfter(req.endDate())) {
      throw ApiExceptions.validationFailed("종료일은 시작일 이후여야 합니다.");
    }
    Project project = new Project(null, principal.organizationId(), req.name(), req.startDate(),
        req.endDate(), req.description(), req.contractorName(), ProjectStatus.PLANNING, null, null,
        null, null);
    UUID projectId =
        projectRepository.insert(project, passwordEncoder.encode(req.deletePassword()));
    seedWorkProducts(projectId);
    UUID dashboardId = createDefaultDashboard(projectId, principal.userId());
    return get(projectId, principal, dashboardId);
  }

  @Transactional(readOnly = true)
  public PageResponse<ProjectSummaryResponse> list(ProjectStatus status, String q,
      PageQuery page, AuthPrincipal principal) {
    var sort = ProjectRepository.sortSpec(page);
    var scope = accessResolver.allowedProjectIds(principal);
    List<Project> rows = projectRepository.search(scope, status, q, sort, page);
    long total = projectRepository.countSearch(scope, status, q);
    if (rows.isEmpty()) {
      return PageResponse.of(List.of(), page, total);
    }
    List<UUID> ids = rows.stream().map(Project::id).toList();
    Map<UUID, ProjectMetricsReader.Card> metrics = metricsReader.metricsOf(ids);
    Map<UUID, String> clientNames = clientOrgNamesOf(rows);
    List<ProjectSummaryResponse> content = rows.stream()
        .map(p -> toSummary(p, metrics.get(p.id()), clientNames.get(p.clientOrgId())))
        .toList();
    return PageResponse.of(content, page, total);
  }

  @Transactional(readOnly = true)
  public ProjectDetailResponse get(UUID projectId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    return get(projectId, principal, null);
  }

  @Transactional
  public ProjectDetailResponse update(UUID projectId, ProjectUpdateRequest req,
      AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    Project existing = projectRepository.findById(projectId)
        .orElseThrow(() -> ApiExceptions.notFound("project", projectId));
    if (existing.status() == ProjectStatus.CLOSED) {
      throw ApiExceptions.projectClosed(projectId);
    }
    if (req.startDate() != null && req.endDate() != null && req.startDate().isAfter(req.endDate())) {
      throw ApiExceptions.validationFailed("종료일은 시작일 이후여야 합니다.");
    }
    projectRepository.update(projectId, req.name(), req.startDate(), req.endDate(),
        req.description(), req.contractorName(), req.currentSiPhase());
    return get(projectId, principal, null);
  }

  private ProjectDetailResponse get(UUID projectId, AuthPrincipal principal, UUID defaultDashboardId) {
    Project p = projectRepository.findById(projectId)
        .orElseThrow(() -> ApiExceptions.notFound("project", projectId));
    String clientOrgName = organizationRepository.findById(p.clientOrgId())
        .map(Organization::name).orElse("");
    int assignmentCount = assignmentRepository.findByProjectId(projectId).size();
    int connectionCount = countConnections(projectId);
    if (defaultDashboardId == null) {
      defaultDashboardId = findDefaultDashboardId(projectId);
    }
    Map<UUID, ProjectMetricsReader.Card> metrics = metricsReader.metricsOf(List.of(projectId));
    ProjectMetrics detailMetrics = metricsReader.toDetailMetrics(metrics.get(projectId));
    return new ProjectDetailResponse(p.id(), p.name(), p.description(), p.contractorName(), p.status(),
        p.startDate(), p.endDate(), p.currentSiPhase(), p.clientOrgId(), clientOrgName,
        assignmentCount, connectionCount, defaultDashboardId, detailMetrics,
        p.createdAt(), p.updatedAt());
  }

  private void seedWorkProducts(UUID projectId) {
    for (String[] row : WORK_PRODUCT_SEED) {
      jdbcClient.sql("""
          insert into work_product (project_id, type, pm_activity, si_activity)
          values (:projectId, :type, :pmActivity, :siActivity)
          """)
          .param("projectId", projectId)
          .param("type", row[0])
          .param("pmActivity", row[1])
          .param("siActivity", row[2])
          .update();
    }
  }

  private UUID createDefaultDashboard(UUID projectId, UUID ownerUserId) {
    return jdbcClient.sql("""
        insert into dashboard (project_id, owner_user_id, name, is_default)
        values (:projectId, :ownerUserId, '사업 현황', true)
        returning id
        """)
        .param("projectId", projectId)
        .param("ownerUserId", ownerUserId)
        .query(UUID.class)
        .single();
  }

  private int countConnections(UUID projectId) {
    Integer c = jdbcClient.sql("select count(*) from tool_connection where project_id = :id")
        .param("id", projectId)
        .query(Integer.class)
        .single();
    return c == null ? 0 : c;
  }

  private UUID findDefaultDashboardId(UUID projectId) {
    return jdbcClient.sql("""
        select id from dashboard
         where project_id = :projectId and is_default and status = 'ACTIVE'
        """)
        .param("projectId", projectId)
        .query(UUID.class)
        .optional()
        .orElse(null);
  }

  private Map<UUID, String> clientOrgNamesOf(List<Project> rows) {
    Map<UUID, String> names = new HashMap<>();
    for (Project p : rows) {
      names.computeIfAbsent(p.clientOrgId(), id ->
          organizationRepository.findById(id).map(Organization::name).orElse(""));
    }
    return names;
  }

  private ProjectSummaryResponse toSummary(Project p, ProjectMetricsReader.Card card,
      String clientOrgName) {
    return new ProjectSummaryResponse(p.id(), p.name(), p.status(), p.startDate(), p.endDate(),
        p.currentSiPhase(), p.clientOrgId(), clientOrgName, p.contractorName(),
        card == null ? 0 : (int) card.workProductApproved(),
        card == null ? 22 : card.workProductTotal(),
        card == null ? 0 : (int) card.openCorrectionActionCount(),
        card == null ? 0 : (int) card.riskOpen(),
        p.updatedAt());
  }
}
