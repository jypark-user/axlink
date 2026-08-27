package kr.co.axlink.flow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.support.AbstractHttpFlowTest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

@Transactional
class AccessIsolationFlowTest extends AbstractHttpFlowTest {

  private static final UUID DEV_CONTRACTOR_USER_ID =
      UUID.fromString("d0000000-0000-4000-8000-000000000003");

  @Autowired
  private JdbcClient jdbcClient;

  private String contractorToken;
  private String clientToken;

  @BeforeEach
  void loginBothRoles() throws Exception {
    contractorToken = loginAs(CONTRACTOR_EMAIL);
    clientToken = loginAs(CLIENT_EMAIL);
  }

  @Test
  void contractorProjectCreateIsForbiddenNotInternalError() throws Exception {
    MvcResult result = mvc.perform(post("/api/projects")
        .header(HttpHeaders.AUTHORIZATION, contractorToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "name", "용역사 생성 시도",
            "startDate", "2026-03-02",
            "endDate", "2026-12-31",
            "description", "거부되어야 한다",
            "deletePassword", "pw-1234"))))
        .andReturn();
    assertThat(result.getResponse().getStatus())
        .as("용역사 프로젝트 생성은 403 이어야 한다(500 이면 회귀): %s", text(result))
        .isEqualTo(403);
    assertThat(body(result).get("code").asText()).isEqualTo("ROLE_FORBIDDEN");
    assertThat(body(result).get("path").asText()).isEqualTo("/api/projects");
  }

  @Test
  void contractorCannotReadUnassignedProject() throws Exception {
    UUID unassigned = insertUnassignedProject();

    MvcResult forbidden = mvc.perform(get("/api/projects/" + unassigned)
        .header(HttpHeaders.AUTHORIZATION, contractorToken))
        .andExpect(status().isForbidden())
        .andReturn();
    assertThat(body(forbidden).get("code").asText())
        .as("미할당 프로젝트 조회는 PROJECT_ACCESS_DENIED 여야 한다: %s", text(forbidden))
        .isEqualTo("PROJECT_ACCESS_DENIED");

    MvcResult listed = mvc.perform(get("/api/projects")
        .header(HttpHeaders.AUTHORIZATION, contractorToken)
        .param("size", "100"))
        .andExpect(status().isOk())
        .andReturn();
    assertThat(text(listed))
        .as("프로젝트 목록에도 미할당 프로젝트가 새어 나오면 안 된다")
        .doesNotContain(unassigned.toString());

    mvc.perform(get("/api/projects/" + unassigned)
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk());
  }

  @Test
  void contractorCannotCallAssignmentApis() throws Exception {
    MvcResult created = mvc.perform(post("/api/projects/" + SEED_PROJECT_ID + "/assignments")
        .header(HttpHeaders.AUTHORIZATION, contractorToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "contractorOrgId", SEED_CONTRACTOR_ORG_ID,
            "userIds", List.of(DEV_CONTRACTOR_USER_ID)))))
        .andExpect(status().isForbidden())
        .andReturn();
    assertThat(body(created).get("code").asText())
        .as("용역사의 할당 생성은 ROLE_FORBIDDEN 이어야 한다: %s", text(created))
        .isEqualTo("ROLE_FORBIDDEN");

    mvc.perform(get("/api/projects/" + SEED_PROJECT_ID + "/assignments")
        .header(HttpHeaders.AUTHORIZATION, contractorToken))
        .andExpect(status().isForbidden());
  }

  @Test
  void askOnUnknownConversationStreamsErrorEventInsteadOfHangingOrFailing() throws Exception {
    UUID unknownId = UUID.randomUUID();
    MvcResult started = mvc.perform(post("/api/conversations/" + unknownId + "/messages")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.TEXT_EVENT_STREAM)
        .content(json(Map.of("question", "없는 대화에 질문", "projectScope", List.of()))))
        .andExpect(request().asyncStarted())
        .andReturn();

    MvcResult dispatched = mvc.perform(asyncDispatch(started))
        .andExpect(status().isOk())
        .andReturn();
    String stream = text(dispatched);
    assertThat(stream)
        .as("없는 대화 id 의 SSE 는 event:error 로 원인을 전달해야 한다: %s", stream)
        .contains("event:error")
        .contains("RESOURCE_NOT_FOUND");
  }

  private UUID insertUnassignedProject() {
    UUID id = UUID.randomUUID();
    jdbcClient.sql("""
        insert into project (id, client_org_id, name, start_date, end_date, description, status)
        values (:id, :orgId, :name, date '2026-01-01', date '2026-12-31', '격리 검증용', 'ACTIVE')
        """)
        .param("id", id)
        .param("orgId", SEED_CLIENT_ORG_ID)
        .param("name", "미할당 프로젝트 " + id)
        .update();
    return id;
  }
}
