package kr.co.axlink.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetOptions;
import kr.co.axlink.dashboard.dto.WidgetQuery;
import kr.co.axlink.dashboard.dto.WidgetSpec;
import kr.co.axlink.semantic.service.SemanticQueryExecutor;
import kr.co.axlink.support.AbstractIntegrationTest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;

@Transactional
class ProjectAccessIsolationTest extends AbstractIntegrationTest {

  private static final UUID OTHER_PROJECT_ID =
      UUID.fromString("c0000000-0000-4000-8000-0000000000aa");

  @Autowired
  private JdbcClient jdbcClient;
  @Autowired
  private SemanticQueryExecutor executor;
  @Autowired
  private ProjectAccessResolver accessResolver;

  @BeforeEach
  void seedSecondProject() {
    jdbcClient.sql("""
        insert into project (id, client_org_id, name, start_date, end_date, description, status)
        values (:id, :orgId, '미할당 프로젝트', date '2026-01-01', date '2026-12-31', '격리 검증용', 'ACTIVE')
        """)
        .param("id", OTHER_PROJECT_ID)
        .param("orgId", SEED_CLIENT_ORG_ID)
        .update();
    insertIssue(SEED_PROJECT_ID, "할당된 프로젝트 이슈");
    insertIssue(OTHER_PROJECT_ID, "미할당 프로젝트 이슈");
  }

  @Test
  void contractorSeesOnlyAssignedProjects() {
    Set<UUID> allowed = inRequestScope(() -> resolver().allowedProjectIds(contractorPrincipal()));
    assertThat(allowed).containsExactly(SEED_PROJECT_ID);
    assertThat(allowed).doesNotContain(OTHER_PROJECT_ID);
  }

  @Test
  void contractorAggregateExcludesUnassignedProjectRows() {
    WidgetDataResponse data = inRequestScope(
        () -> executor.run(openIssueCountByProject(null), contractorPrincipal(), null));
    List<Object> projectKeys = data.rows().stream().map(row -> row.values().get("d0")).toList();
    assertThat(projectKeys).containsExactly(SEED_PROJECT_ID.toString());
  }

  @Test
  void clientOfOwningOrgSeesBothProjects() {
    WidgetDataResponse data = inRequestScope(
        () -> executor.run(openIssueCountByProject(null), clientPrincipal(), null));
    List<Object> projectKeys = data.rows().stream().map(row -> row.values().get("d0")).toList();
    assertThat(projectKeys).contains(SEED_PROJECT_ID.toString(), OTHER_PROJECT_ID.toString());
  }

  @Test
  void contractorRequestingUnassignedProjectScopeIsDenied() {
    assertThatThrownBy(() -> inRequestScope(
        () -> executor.run(openIssueCountByProject(List.of(OTHER_PROJECT_ID)),
            contractorPrincipal(), null)))
        .isInstanceOf(ApiException.class);
  }

  @Test
  void contractorCannotRequireUnassignedProject() {
    assertThatThrownBy(() -> inRequestScope(() -> {
      resolver().requireProject(contractorPrincipal(), OTHER_PROJECT_ID);
      return null;
    })).isInstanceOf(ApiException.class);
  }

  private ProjectAccessResolver resolver() {
    return accessResolver;
  }

  private WidgetSpec openIssueCountByProject(List<UUID> scope) {
    return new WidgetSpec(WidgetTemplate.BAR_CHART, "열린 이슈 수",
        new WidgetQuery("open_issue_count", List.of("project"), List.of(), scope, 20),
        new WidgetOptions(null, "desc", null, null, null, null, null));
  }

  private void insertIssue(UUID projectId, String title) {
    jdbcClient.sql("""
        insert into issue (project_id, title, status, severity, source_created_at)
        values (:projectId, :title, 'OPEN', 'MAJOR', now())
        """)
        .params(Map.of("projectId", projectId, "title", title))
        .update();
  }
}
