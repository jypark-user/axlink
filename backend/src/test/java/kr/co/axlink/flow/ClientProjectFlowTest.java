package kr.co.axlink.flow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.support.AbstractHttpFlowTest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.annotation.Transactional;

@Transactional
class ClientProjectFlowTest extends AbstractHttpFlowTest {

  private static final UUID DEV_CONTRACTOR_USER_ID =
      UUID.fromString("d0000000-0000-4000-8000-000000000003");

  private String clientToken;

  @BeforeEach
  void loginAsClient() throws Exception {
    clientToken = loginAs(CLIENT_EMAIL);
  }

  @Test
  void unauthenticatedProjectListIsRejectedWithUnauthorized() throws Exception {
    MvcResult result = mvc.perform(get("/api/projects"))
        .andExpect(status().isUnauthorized())
        .andReturn();
    assertThat(body(result).get("code").asText())
        .as("미인증 요청은 AUTH_TOKEN_INVALID 로 거부되어야 한다: %s", text(result))
        .isEqualTo("AUTH_TOKEN_INVALID");
  }

  @Test
  void clientCreatesProjectWithFourFields() throws Exception {
    String name = uniqueName();
    MvcResult result = createProjectRequest(name, "2026-03-02", "2026-12-31")
        .andExpect(status().isCreated())
        .andReturn();
    JsonNode created = body(result);
    assertThat(created.get("name").asText()).isEqualTo(name);
    assertThat(created.get("startDate").asText()).isEqualTo("2026-03-02");
    assertThat(created.get("endDate").asText()).isEqualTo("2026-12-31");
    assertThat(created.get("description").asText()).isEqualTo("종단 통합 테스트 사업");

    MvcResult fetched = mvc.perform(get("/api/projects/" + created.get("id").asText())
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    assertThat(body(fetched).get("name").asText())
        .as("생성 직후 단건 조회가 같은 프로젝트를 돌려주어야 한다: %s", text(fetched))
        .isEqualTo(name);
  }

  @Test
  void projectCreateRejectsStartDateAfterEndDate() throws Exception {
    MvcResult result = createProjectRequest(uniqueName(), "2026-12-31", "2026-03-02")
        .andExpect(status().isBadRequest())
        .andReturn();
    assertThat(body(result).get("code").asText())
        .as("착수일이 마감일보다 늦으면 VALIDATION_FAILED 여야 한다: %s", text(result))
        .isEqualTo("VALIDATION_FAILED");
  }

  @Test
  void assignedContractorAppearsInAssignmentList() throws Exception {
    UUID projectId = createProject();
    JsonNode created = assign(projectId);
    assertThat(created).hasSize(1);

    MvcResult listed = mvc.perform(get("/api/projects/" + projectId + "/assignments")
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    List<String> userIds = new ArrayList<>();
    body(listed).forEach(node -> userIds.add(node.get("userId").asText()));
    assertThat(userIds)
        .as("할당한 용역사 계정이 할당 목록에 나타나야 한다: %s", text(listed))
        .containsExactly(DEV_CONTRACTOR_USER_ID.toString());
  }

  private JsonNode assign(UUID projectId) throws Exception {
    MvcResult result = mvc.perform(post("/api/projects/" + projectId + "/assignments")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "contractorOrgId", SEED_CONTRACTOR_ORG_ID,
            "userIds", List.of(DEV_CONTRACTOR_USER_ID)))))
        .andExpect(status().isCreated())
        .andReturn();
    return body(result);
  }

  private ResultActions createProjectRequest(String name, String startDate, String endDate)
      throws Exception {
    return mvc.perform(post("/api/projects")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "name", name,
            "startDate", startDate,
            "endDate", endDate,
            "description", "종단 통합 테스트 사업",
            "deletePassword", "pw-1234"))));
  }

  private UUID createProject() throws Exception {
    MvcResult result = createProjectRequest(uniqueName(), "2026-03-02", "2026-12-31")
        .andExpect(status().isCreated())
        .andReturn();
    return UUID.fromString(body(result).get("id").asText());
  }

  private static String uniqueName() {
    return "종단 테스트 사업 " + UUID.randomUUID();
  }
}
