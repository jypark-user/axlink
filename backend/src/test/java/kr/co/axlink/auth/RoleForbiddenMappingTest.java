package kr.co.axlink.auth;

import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import kr.co.axlink.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@AutoConfigureMockMvc
class RoleForbiddenMappingTest extends AbstractIntegrationTest {

  private static final String BODY = """
      {"name":"권한거부검증","startDate":"2026-01-01","endDate":"2026-06-01","description":"d",
       "deletePassword":"pw-1234"}
      """;

  @Autowired
  private MockMvc mockMvc;

  @Test
  void contractorProjectCreateIsForbiddenNotInternalError() throws Exception {
    mockMvc.perform(post("/api/projects")
            .with(user("contractor").roles("CONTRACTOR"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(BODY))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("ROLE_FORBIDDEN"))
        .andExpect(jsonPath("$.path").value("/api/projects"));
  }

  /** 용역사는 AI Q&A·LLM 기능을 쓰지 않는다 — SecurityConfig 의 EXCEPT_CONTRACTOR 가 살아 있는지 본다. */
  @Test
  void contractorCannotReachAiQnA() throws Exception {
    mockMvc.perform(get("/api/conversations").with(user("contractor").roles("CONTRACTOR")))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("ROLE_FORBIDDEN"));
  }

  /** 용역사에게 닫힌 발주사 화면 표본. 전부 같은 매처를 타므로 하나만 검증한다. */
  @Test
  void contractorCannotReachClientOnlyScreens() throws Exception {
    mockMvc.perform(get("/api/projects/00000000-0000-0000-0000-000000000001/traceability")
            .with(user("contractor").roles("CONTRACTOR")))
        .andExpect(status().isForbidden());
  }

  /** 매처가 너무 넓지 않은지 — 발주사는 인가 단계를 그대로 통과해야 한다. */
  @Test
  void clientStillReachesAiQnA() throws Exception {
    mockMvc.perform(get("/api/conversations").with(user("client").roles("CLIENT")))
        .andExpect(status().is(not(403)));
  }

  /** 용역사에게 열어 둔 연동 목록은 막히면 안 된다. */
  @Test
  void contractorStillReachesConnections() throws Exception {
    mockMvc.perform(get("/api/projects/00000000-0000-0000-0000-000000000001/connections")
            .with(user("contractor").roles("CONTRACTOR")))
        .andExpect(status().is(not(403)));
  }

  @Test
  void superAdminProjectCreateIsForbiddenNotInternalError() throws Exception {
    mockMvc.perform(post("/api/projects")
            .with(user("admin").roles("SUPER_ADMIN"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(BODY))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("ROLE_FORBIDDEN"));
  }
}
