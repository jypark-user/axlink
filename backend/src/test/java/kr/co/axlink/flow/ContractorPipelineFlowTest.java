package kr.co.axlink.flow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
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
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

@Transactional
class ContractorPipelineFlowTest extends AbstractHttpFlowTest {

  private static final String RAW_API_TOKEN = "e2e-github-secret-9f3a2b7c";

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
  void toolConnectionStoresTokenEncryptedAndExposesOnlyMask() throws Exception {
    MvcResult created = mvc.perform(post("/api/projects/" + SEED_PROJECT_ID + "/connections")
        .header(HttpHeaders.AUTHORIZATION, contractorToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "tool", "GITHUB",
            "name", "종단 테스트 GitHub",
            "baseUrl", "https://api.github.com",
            "targetResource", "axlink/e2e",
            "credential", Map.of("accessToken", RAW_API_TOKEN)))))
        .andExpect(status().isCreated())
        .andReturn();
    JsonNode body = body(created);
    UUID connectionId = UUID.fromString(body.get("id").asText());
    assertThat(text(created))
        .as("생성 응답 어디에도 원문 토큰이 나오면 안 된다")
        .doesNotContain(RAW_API_TOKEN);
    assertThat(body.get("credentialMasked").asText())
        .as("마스킹된 자격증명이 내려와야 한다: %s", text(created))
        .isNotBlank()
        .doesNotContain(RAW_API_TOKEN);

    String stored = jdbcClient.sql("select auth_encrypted from tool_connection where id = :id")
        .param("id", connectionId).query(String.class).single();
    assertThat(stored)
        .as("DB 에는 암호화된 값만 저장되어야 한다")
        .isNotBlank()
        .doesNotContain(RAW_API_TOKEN);

    MvcResult fetched = mvc.perform(get("/api/connections/" + connectionId)
        .header(HttpHeaders.AUTHORIZATION, contractorToken))
        .andExpect(status().isOk())
        .andReturn();
    assertThat(text(fetched))
        .as("단건 조회에서도 원문 토큰이 노출되면 안 된다")
        .doesNotContain(RAW_API_TOKEN);
    assertThat(body(fetched).get("credentialMasked").asText())
        .isEqualTo(body.get("credentialMasked").asText());

    MvcResult listed = mvc.perform(get("/api/projects/" + SEED_PROJECT_ID + "/connections")
        .header(HttpHeaders.AUTHORIZATION, contractorToken))
        .andExpect(status().isOk())
        .andReturn();
    List<String> ids = new ArrayList<>();
    body(listed).forEach(node -> ids.add(node.get("id").asText()));
    assertThat(ids)
        .as("등록한 연동이 프로젝트 연동 목록에 나타나야 한다: %s", text(listed))
        .contains(connectionId.toString());
  }

  @Test
  void toolConnectionRejectsPlainHttpBaseUrl() throws Exception {
    MvcResult result = mvc.perform(post("/api/projects/" + SEED_PROJECT_ID + "/connections")
        .header(HttpHeaders.AUTHORIZATION, contractorToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "tool", "GITHUB",
            "name", "평문 GitHub",
            "baseUrl", "http://api.github.com",
            "targetResource", "axlink/e2e",
            "credential", Map.of("accessToken", RAW_API_TOKEN)))))
        .andExpect(status().isBadRequest())
        .andReturn();
    assertThat(body(result).get("code").asText())
        .as("http baseUrl 은 거부되어야 한다: %s", text(result))
        .isEqualTo("VALIDATION_FAILED");
  }

  /** 상태는 플랫폼이 바꾸지 않는다 — 도구에서 수집한 값이고, 수정일이 가장 최근인 행이 최신이다 (PRD STD-001). */
  @Test
  void checklistShowsCollectedStatusOfTheMostRecentlyUpdatedRow() throws Exception {
    JsonNode before = checklist();
    int approvedBefore = before.get("approvedCount").asInt();
    assertThat(before.get("totalCount").asInt())
        .as("표준 산출물 점검표는 22종이어야 한다: %s", before.toString())
        .isEqualTo(22);

    JsonNode target = firstItemWithStatus(before, "NONE");
    String type = target.get("type").asText();
    UUID collectedId = collectWorkProduct(type, "APPROVED");

    JsonNode after = checklist();
    assertThat(after.get("totalCount").asInt())
        .as("새 버전이 들어와도 점검표는 22종을 유지해야 한다: %s", after.toString())
        .isEqualTo(22);
    assertThat(after.get("approvedCount").asInt())
        .as("수집된 승인 상태가 점검표에 반영되어야 한다: %s", after.toString())
        .isEqualTo(approvedBefore + 1);
    JsonNode row = itemById(after, collectedId);
    assertThat(row.get("status").asText()).isEqualTo("APPROVED");
    assertThat(row.get("type").asText()).isEqualTo(type);
  }

  @Test
  void workProductStatusCannotBeChangedThroughTheApi() throws Exception {
    UUID workProductId = UUID.fromString(firstItemWithStatus(checklist(), "NONE").get("id").asText());
    mvc.perform(patch("/api/work-products/" + workProductId + "/status")
            .header(HttpHeaders.AUTHORIZATION, clientToken)
            .contentType(MediaType.APPLICATION_JSON)
            .content(json(Map.of("status", "DRAFT"))))
        .andExpect(status().isNotFound());
  }

  @Test
  void loadedRequirementAppearsInTraceabilityAndRequirementList() throws Exception {
    String code = "AAA-E2E-" + UUID.randomUUID().toString().substring(0, 8);
    String title = "종단 테스트 요구사항 " + code;
    insertRequirement(code, title);

    MvcResult trace = mvc.perform(get("/api/projects/" + SEED_PROJECT_ID + "/traceability")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .param("size", "100"))
        .andExpect(status().isOk())
        .andReturn();
    List<String> codes = new ArrayList<>();
    body(trace).get("content").forEach(node -> codes.add(node.get("requirementCode").asText()));
    assertThat(codes)
        .as("적재한 요구사항이 추적 매트릭스에 나타나야 한다: %s", text(trace))
        .contains(code);

    MvcResult requirements = mvc.perform(get("/api/projects/" + SEED_PROJECT_ID + "/requirements")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .param("q", code))
        .andExpect(status().isOk())
        .andReturn();
    JsonNode content = body(requirements).get("content");
    assertThat(content)
        .as("요구사항 검색이 적재분을 찾아야 한다: %s", text(requirements))
        .hasSize(1);
    assertThat(content.get(0).get("title").asText()).isEqualTo(title);
    assertThat(content.get(0).get("traceComplete").asBoolean())
        .as("추적 링크가 없으므로 traceComplete 는 false 여야 한다")
        .isFalse();
  }

  @Test
  void contractorIsClosedOutOfClientOnlyScreensOfAssignedProject() throws Exception {
    List<String> closed = List.of(
        "/api/projects/" + SEED_PROJECT_ID + "/work-products",
        "/api/projects/" + SEED_PROJECT_ID + "/requirements",
        "/api/projects/" + SEED_PROJECT_ID + "/traceability",
        "/api/projects/" + SEED_PROJECT_ID + "/documents");
    for (String path : closed) {
      MvcResult result = mvc.perform(get(path)
          .header(HttpHeaders.AUTHORIZATION, contractorToken))
          .andReturn();
      assertThat(result.getResponse().getStatus())
          .as("할당된 프로젝트라도 %s 는 용역사에게 닫혀 있어야 한다", path)
          .isEqualTo(403);
      assertThat(body(result).get("code").asText())
          .as("%s 의 거부는 ROLE_FORBIDDEN 이어야 한다: %s", path, text(result))
          .isEqualTo("ROLE_FORBIDDEN");
    }
  }

  private void insertRequirement(String code, String title) {
    jdbcClient.sql("""
        insert into requirement (project_id, code, title, priority, status, source_kind)
        values (:projectId, :code, :title, 'MUST', 'DEFINED', 'MANUAL')
        """)
        .param("projectId", SEED_PROJECT_ID)
        .param("code", code)
        .param("title", title)
        .update();
  }

  private JsonNode checklist() throws Exception {
    MvcResult result = mvc.perform(get("/api/projects/" + SEED_PROJECT_ID + "/work-products")
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    return body(result);
  }

  /** 도구에서 그 유형의 새 버전을 수집한 상황을 만든다. */
  private UUID collectWorkProduct(String type, String status) {
    return jdbcClient.sql("""
        insert into work_product (project_id, type, version, title, status, applicable, is_current,
                                  pm_activity, si_activity, approved_at, source_kind, created_at, updated_at)
        select cast(:projectId as uuid), cast(:type as varchar), '1', cast(:title as varchar), cast(:status as varchar), true, false,
               w.pm_activity, w.si_activity, now(), 'MANUAL', now(), now()
          from work_product w
         where w.project_id = :projectId and w.type = :type and w.is_current
        returning id
        """)
        .param("projectId", SEED_PROJECT_ID)
        .param("type", type)
        .param("title", "종단 테스트 수집본 " + type)
        .param("status", status)
        .query(UUID.class).single();
  }

  private static JsonNode firstItemWithStatus(JsonNode checklist, String status) {
    for (JsonNode item : checklist.get("items")) {
      if (status.equals(item.get("status").asText())) {
        return item;
      }
    }
    throw new AssertionError("점검표에 " + status + " 상태 산출물이 없다: " + checklist);
  }

  private static JsonNode itemById(JsonNode checklist, UUID workProductId) {
    for (JsonNode item : checklist.get("items")) {
      if (workProductId.toString().equals(item.get("id").asText())) {
        return item;
      }
    }
    throw new AssertionError("점검표에서 " + workProductId + " 를 찾지 못했다: " + checklist);
  }
}
