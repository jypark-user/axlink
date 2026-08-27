package kr.co.axlink.project;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalDate;
import java.util.UUID;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ErrorCode;
import kr.co.axlink.project.service.ProjectClosureService;
import kr.co.axlink.project.service.ProjectService;
import kr.co.axlink.project.web.ClosureCheck;
import kr.co.axlink.project.web.ProjectClosureResponse;
import kr.co.axlink.project.web.ProjectCreateRequest;
import kr.co.axlink.project.web.ProjectDetailResponse;
import kr.co.axlink.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;

@Transactional
class ProjectLifecycleRuleTest extends AbstractIntegrationTest {

  @Autowired
  private ProjectService projectService;
  @Autowired
  private ProjectClosureService closureService;
  @Autowired
  private JdbcClient jdbcClient;

  @Test
  void createRejectsStartDateAfterEndDate() {
    ProjectCreateRequest request = new ProjectCreateRequest("역순 일정 사업",
        LocalDate.of(2026, 12, 31), LocalDate.of(2026, 3, 2), "착수일이 마감일보다 늦다", null, "test1234");
    assertThatThrownBy(() -> inRequestScope(
        () -> projectService.create(request, clientPrincipal())))
        .isInstanceOf(ApiException.class)
        .extracting(e -> ((ApiException) e).code())
        .isEqualTo(ErrorCode.VALIDATION_FAILED);
  }

  @Test
  void createSeedsTwentyTwoWorkProducts() {
    UUID projectId = inRequestScope(() -> createProject()).id();
    Integer count = jdbcClient
        .sql("select count(*) from work_product where project_id = :id and is_current")
        .param("id", projectId)
        .query(Integer.class)
        .single();
    assertThat(count).isEqualTo(22);
  }

  @Test
  void closeIsRejectedWithoutAcceptanceRecord() {
    UUID projectId = inRequestScope(() -> createProject()).id();
    approveAllWorkProducts(projectId);

    ProjectClosureResponse check =
        inRequestScope(() -> closureService.check(projectId, clientPrincipal()));
    assertThat(check.closable()).isFalse();
    assertThat(failedChecks(check)).contains(ClosureCheck.ACCEPTANCE_RECORD_EXISTS);

    assertThatThrownBy(() -> inRequestScope(() -> {
      closureService.close(projectId, clientPrincipal());
      return null;
    }))
        .isInstanceOf(ApiException.class)
        .extracting(e -> ((ApiException) e).code())
        .isEqualTo(ErrorCode.CLOSURE_GATE_UNSATISFIED);
  }

  @Test
  void closeSucceedsOnceEveryGateIsSatisfied() {
    UUID projectId = inRequestScope(() -> createProject()).id();
    approveAllWorkProducts(projectId);
    issueAcceptanceRecord(projectId);

    ProjectClosureResponse check =
        inRequestScope(() -> closureService.check(projectId, clientPrincipal()));
    assertThat(check.closable()).isTrue();

    inRequestScope(() -> {
      closureService.close(projectId, clientPrincipal());
      return null;
    });

    String status = jdbcClient.sql("select status from project where id = :id")
        .param("id", projectId)
        .query(String.class)
        .single();
    assertThat(status).isEqualTo("CLOSED");
  }

  @Test
  void closeIsRejectedWhileWorkProductsAreUnapproved() {
    UUID projectId = inRequestScope(() -> createProject()).id();
    issueAcceptanceRecord(projectId);

    ProjectClosureResponse check =
        inRequestScope(() -> closureService.check(projectId, clientPrincipal()));
    assertThat(check.closable()).isFalse();
    assertThat(failedChecks(check)).contains(ClosureCheck.REQUIRED_WORK_PRODUCTS_APPROVED);
  }

  private ProjectDetailResponse createProject() {
    return projectService.create(new ProjectCreateRequest("종료 규칙 검증 사업",
        LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31), "종료 게이트 검증", null, "test1234"), clientPrincipal());
  }

  private java.util.List<String> failedChecks(ProjectClosureResponse response) {
    return response.checks().stream()
        .filter(check -> !check.satisfied())
        .map(ClosureCheck::key)
        .toList();
  }

  private void approveAllWorkProducts(UUID projectId) {
    jdbcClient.sql("""
        update work_product
           set status = 'APPROVED', approved_at = now(), updated_at = now()
         where project_id = :id and is_current and applicable
        """)
        .param("id", projectId)
        .update();
  }

  private void issueAcceptanceRecord(UUID projectId) {
    jdbcClient.sql("""
        insert into acceptance_record (project_id, accepted_by_user_id, accepted_at, status)
        values (:projectId, :userId, now(), 'ISSUED')
        """)
        .param("projectId", projectId)
        .param("userId", SEED_CLIENT_USER_ID)
        .update();
  }
}
