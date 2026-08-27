package kr.co.axlink.flow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
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
class AnalyticsFlowTest extends AbstractHttpFlowTest {

  @Autowired
  private JdbcClient jdbcClient;

  private String clientToken;

  @BeforeEach
  void loginAsClient() throws Exception {
    clientToken = loginAs(CLIENT_EMAIL);
  }

  @Test
  void semanticCatalogExposesMeasuresDimensionsAndFilters() throws Exception {
    MvcResult result = mvc.perform(get("/api/semantic/catalog")
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    JsonNode catalog = body(result);
    List<String> measureKeys = new ArrayList<>();
    catalog.get("measures").forEach(node -> measureKeys.add(node.get("key").asText()));
    assertThat(measureKeys)
        .as("카탈로그 measure 목록이 비어 있으면 안 된다: %s", text(result))
        .isNotEmpty()
        .contains("open_issue_count");
    assertThat(catalog.get("dimensions")).isNotEmpty();
    assertThat(catalog.get("filters")).isNotEmpty();

    MvcResult measure = mvc.perform(get("/api/semantic/measures/open_issue_count")
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    List<String> allowed = new ArrayList<>();
    body(measure).get("allowedDimensions").forEach(node -> allowed.add(node.asText()));
    assertThat(allowed)
        .as("open_issue_count 는 project 차원을 허용해야 한다: %s", text(measure))
        .contains("project");
  }

  @Test
  void widgetPreviewReturnsRowsScopedToAllowedProjects() throws Exception {
    insertOpenIssue(SEED_PROJECT_ID, "종단 테스트 이슈 " + UUID.randomUUID());

    MvcResult result = mvc.perform(post("/api/widgets/preview")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("spec", barChartSpec()))))
        .andExpect(status().isOk())
        .andReturn();
    JsonNode data = body(result);
    assertThat(data.get("measure").asText()).isEqualTo("open_issue_count");
    assertThat(data.get("rows"))
        .as("적재한 이슈가 있으므로 위젯 실행 결과가 비어 있으면 안 된다: %s", text(result))
        .isNotEmpty();

    List<String> allowedProjectIds = allowedProjectIdsOfMe();
    List<String> appliedProjectIds = new ArrayList<>();
    data.get("appliedProjectIds").forEach(node -> appliedProjectIds.add(node.asText()));
    assertThat(appliedProjectIds)
        .as("위젯은 allowedProjectIds 범위를 벗어나면 안 된다: applied=%s allowed=%s",
            appliedProjectIds, allowedProjectIds)
        .isNotEmpty()
        .isSubsetOf(allowedProjectIds);

    List<String> rowProjectIds = new ArrayList<>();
    data.get("rows").forEach(row -> rowProjectIds.add(row.get("values").get("d0").asText()));
    assertThat(rowProjectIds)
        .as("행 단위로도 허용 프로젝트만 나와야 한다: %s", text(result))
        .isSubsetOf(allowedProjectIds);
  }

  @Test
  void dashboardLayoutIsPersistedOnServerAndRestoredOnReread() throws Exception {
    UUID dashboardId = createDashboard();
    UUID widgetId = createWidget(dashboardId);

    Map<String, Object> item = new LinkedHashMap<>();
    item.put("i", widgetId.toString());
    item.put("x", 3);
    item.put("y", 7);
    item.put("w", 6);
    item.put("h", 4);
    item.put("minW", 2);
    item.put("minH", 2);
    Map<String, Object> layout = Map.of(
        "lg", List.of(item), "md", List.of(item), "sm", List.of(item));

    mvc.perform(put("/api/dashboards/" + dashboardId + "/layout")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("layout", layout))))
        .andExpect(status().isOk());

    MvcResult reread = mvc.perform(get("/api/dashboards/" + dashboardId)
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    JsonNode lg = body(reread).get("layout").get("lg");
    assertThat(lg)
        .as("레이아웃이 서버에 저장되어 재조회 시 복원되어야 한다: %s", text(reread))
        .hasSize(1);
    assertThat(lg.get(0).get("i").asText()).isEqualTo(widgetId.toString());
    assertThat(lg.get(0).get("x").asInt()).isEqualTo(3);
    assertThat(lg.get(0).get("y").asInt()).isEqualTo(7);
    assertThat(lg.get(0).get("w").asInt()).isEqualTo(6);
    assertThat(lg.get(0).get("h").asInt()).isEqualTo(4);
  }

  @Test
  void conversationCreateThenMessageListSucceeds() throws Exception {
    MvcResult created = mvc.perform(post("/api/conversations")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "title", "종단 테스트 대화 " + UUID.randomUUID(),
            "projectScope", List.of(SEED_PROJECT_ID)))))
        .andExpect(status().isCreated())
        .andReturn();
    UUID conversationId = UUID.fromString(body(created).get("id").asText());

    MvcResult messages = mvc.perform(get("/api/conversations/" + conversationId + "/messages")
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    assertThat(body(messages).isArray())
        .as("새 대화의 메시지 목록은 빈 배열이어야 한다: %s", text(messages))
        .isTrue();
    assertThat(body(messages)).isEmpty();

    MvcResult listed = mvc.perform(get("/api/conversations")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .param("size", "100"))
        .andExpect(status().isOk())
        .andReturn();
    List<String> ids = new ArrayList<>();
    body(listed).get("content").forEach(node -> ids.add(node.get("id").asText()));
    assertThat(ids)
        .as("생성한 대화가 목록에 나타나야 한다: %s", text(listed))
        .contains(conversationId.toString());
  }

  private List<String> allowedProjectIdsOfMe() throws Exception {
    MvcResult me = mvc.perform(get("/api/auth/me")
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    List<String> allowed = new ArrayList<>();
    body(me).get("allowedProjectIds").forEach(node -> allowed.add(node.asText()));
    return allowed;
  }

  private UUID createDashboard() throws Exception {
    MvcResult result = mvc.perform(post("/api/dashboards")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of(
            "name", "종단 테스트 대시보드 " + UUID.randomUUID(),
            "projectId", SEED_PROJECT_ID))))
        .andExpect(status().isCreated())
        .andReturn();
    return UUID.fromString(body(result).get("id").asText());
  }

  private UUID createWidget(UUID dashboardId) throws Exception {
    MvcResult result = mvc.perform(post("/api/dashboards/" + dashboardId + "/widgets")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("spec", barChartSpec()))))
        .andExpect(status().isCreated())
        .andReturn();
    return UUID.fromString(body(result).get("id").asText());
  }

  private static Map<String, Object> barChartSpec() {
    Map<String, Object> query = new LinkedHashMap<>();
    query.put("measure", "open_issue_count");
    query.put("dimensions", List.of("project"));
    query.put("filters", List.of());
    query.put("limit", 20);
    Map<String, Object> options = new LinkedHashMap<>();
    options.put("sort", "desc");
    Map<String, Object> spec = new LinkedHashMap<>();
    spec.put("template", "BAR_CHART");
    spec.put("title", "열린 이슈 수");
    spec.put("query", query);
    spec.put("options", options);
    return spec;
  }

  private void insertOpenIssue(UUID projectId, String title) {
    jdbcClient.sql("""
        insert into issue (project_id, title, status, severity, source_created_at)
        values (:projectId, :title, 'OPEN', 'MAJOR', now())
        """)
        .param("projectId", projectId)
        .param("title", title)
        .update();
  }
}
