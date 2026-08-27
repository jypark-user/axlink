package kr.co.axlink.project.service;

import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.error.ErrorCode;
import kr.co.axlink.project.domain.Project;
import kr.co.axlink.project.repository.ProjectRepository;
import kr.co.axlink.project.web.ClosureCheck;
import kr.co.axlink.project.web.ProjectClosureResponse;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProjectClosureService {

  private final ProjectRepository projectRepository;
  private final ProjectAccessResolver accessResolver;
  private final JdbcClient jdbcClient;
  private final Clock clock;

  public ProjectClosureService(ProjectRepository projectRepository,
      ProjectAccessResolver accessResolver, JdbcClient jdbcClient, Clock clock) {
    this.projectRepository = projectRepository;
    this.accessResolver = accessResolver;
    this.jdbcClient = jdbcClient;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public ProjectClosureResponse check(UUID projectId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    return evaluate(projectId);
  }

  @Transactional
  public void close(UUID projectId, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    ProjectClosureResponse result = evaluate(projectId);
    if (!result.closable()) {
      throw new ApiException(ErrorCode.CLOSURE_GATE_UNSATISFIED,
          "종료 조건을 충족하지 못했습니다.");
    }
    projectRepository.close(projectId, clock.instant());
  }

  private ProjectClosureResponse evaluate(UUID projectId) {
    Project project = projectRepository.findById(projectId)
        .orElseThrow(() -> ApiExceptions.notFound("project", projectId));
    List<ClosureCheck> checks = new ArrayList<>();

    boolean acceptance = existsAcceptance(projectId);
    checks.add(new ClosureCheck(ClosureCheck.ACCEPTANCE_RECORD_EXISTS, acceptance,
        acceptance ? "인수기록이 존재합니다." : "유효한 인수기록이 없습니다."));

    int unapproved = countUnapprovedRequiredWorkProducts(projectId);
    boolean wpOk = unapproved == 0;
    checks.add(new ClosureCheck(ClosureCheck.REQUIRED_WORK_PRODUCTS_APPROVED, wpOk,
        wpOk ? "필수 산출물이 모두 승인되었습니다."
             : "미승인 필수 산출물 " + unapproved + "건이 남아 있습니다."));

    int openCorrections = countOpenCorrections(projectId);
    boolean corrOk = openCorrections == 0;
    checks.add(new ClosureCheck(ClosureCheck.NO_OPEN_CORRECTION_ACTION, corrOk,
        corrOk ? "미완료 시정조치가 없습니다."
               : "미완료 시정조치 " + openCorrections + "건이 남아 있습니다."));

    boolean closable = acceptance && wpOk && corrOk;
    return new ProjectClosureResponse(projectId, closable, checks);
  }

  private boolean existsAcceptance(UUID projectId) {
    return jdbcClient.sql("""
        select 1 from acceptance_record
         where project_id = :projectId and status = 'ISSUED'
        """)
        .param("projectId", projectId)
        .query(Integer.class)
        .optional()
        .isPresent();
  }

  private int countUnapprovedRequiredWorkProducts(UUID projectId) {
    Integer c = jdbcClient.sql("""
        select count(*) from work_product
         where project_id = :projectId and is_current and applicable
           and status <> 'APPROVED'
        """)
        .param("projectId", projectId)
        .query(Integer.class)
        .single();
    return c == null ? 0 : c;
  }

  private int countOpenCorrections(UUID projectId) {
    Integer c = jdbcClient.sql("""
        select count(*) from correction_action
         where project_id = :projectId and status = 'OPEN'
        """)
        .param("projectId", projectId)
        .query(Integer.class)
        .single();
    return c == null ? 0 : c;
  }
}
