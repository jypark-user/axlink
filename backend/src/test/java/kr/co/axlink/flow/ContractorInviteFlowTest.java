package kr.co.axlink.flow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.support.AbstractHttpFlowTest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

/** 초대 링크 → 용역사 자가 가입 → 프로젝트 자동 할당. */
@Transactional
class ContractorInviteFlowTest extends AbstractHttpFlowTest {

  private String clientToken;

  @BeforeEach
  void loginAsClient() throws Exception {
    clientToken = loginAs(CLIENT_EMAIL);
  }

  @Test
  void inviteLinkLetsContractorCreateAccountAndJoinProject() throws Exception {
    String orgName = "초대테스트용역사-" + UUID.randomUUID();
    JsonNode invite = createInvite();
    String token = invite.get("token").asText();
    assertThat(token).as("생성 응답에는 원본 토큰이 담겨야 한다").isNotBlank();

    MvcResult preview = mvc.perform(get("/api/auth/invitations/" + token))
        .andExpect(status().isOk())
        .andReturn();
    assertThat(body(preview).get("kind").asText()).isEqualTo("PROJECT");
    assertThat(body(preview).get("projectName").asText()).isNotBlank();

    String email = "invitee-" + UUID.randomUUID() + "@contractor.test";
    MvcResult accepted = mvc.perform(post("/api/auth/invitations/accept")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("token", token, "contractorOrgName", orgName, "email", email,
            "name", "김용역", "password", "invite1234"))))
        .andExpect(status().isOk())
        .andReturn();
    JsonNode user = body(accepted).get("user");
    assertThat(user.get("role").asText()).isEqualTo("CONTRACTOR");
    assertThat(user.get("organizationName").asText()).isEqualTo(orgName);
    assertThat(user.get("allowedProjectIds")).as("가입 즉시 초대된 프로젝트에 접근할 수 있어야 한다")
        .anySatisfy(id -> assertThat(id.asText()).isEqualTo(SEED_PROJECT_ID.toString()));

    MvcResult assignments = mvc.perform(get(assignmentsPath())
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isOk())
        .andReturn();
    assertThat(body(assignments)).anySatisfy(a -> {
      assertThat(a.get("userEmail").asText()).isEqualTo(email);
      assertThat(a.get("contractorOrgName").asText()).isEqualTo(orgName);
      assertThat(a.get("status").asText()).as("가입 즉시 활성 할당이어야 한다").isEqualTo("ACTIVE");
    });
  }

  @Test
  void revokedLinkIsRejected() throws Exception {
    JsonNode invite = createInvite();
    String token = invite.get("token").asText();

    mvc.perform(delete(invitesPath() + "/" + invite.get("id").asText())
            .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isNoContent());

    mvc.perform(get("/api/auth/invitations/" + token))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void duplicateEmailIsRejected() throws Exception {
    JsonNode invite = createInvite();
    mvc.perform(post("/api/auth/invitations/accept")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("token", invite.get("token").asText(),
            "contractorOrgName", "중복테스트용역사", "email", CONTRACTOR_EMAIL,
            "name", "중복", "password", "invite1234"))))
        .andExpect(status().isConflict());
  }

  @Test
  void weakPasswordIsRejected() throws Exception {
    JsonNode invite = createInvite();
    mvc.perform(post("/api/auth/invitations/accept")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("token", invite.get("token").asText(),
            "contractorOrgName", "약한암호용역사",
            "email", "weak-" + UUID.randomUUID() + "@contractor.test",
            "name", "약함", "password", "abcdefgh"))))
        .andExpect(status().isBadRequest());
  }

  @Test
  void adminInviteLinkLetsInvitedAccountSetItsOwnPassword() throws Exception {
    String adminToken = loginAs(ADMIN_EMAIL);
    String email = "invited-" + UUID.randomUUID() + "@client.test";
    MvcResult createdUser = mvc.perform(post("/api/users")
        .header(HttpHeaders.AUTHORIZATION, adminToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("organizationId", SEED_CLIENT_ORG_ID.toString(), "email", email,
            "name", "신규담당", "role", "CLIENT"))))
        .andExpect(status().isCreated())
        .andReturn();
    String userId = body(createdUser).get("id").asText();

    MvcResult link = mvc.perform(post("/api/users/" + userId + "/invitation-link")
        .header(HttpHeaders.AUTHORIZATION, adminToken)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{}"))
        .andExpect(status().isOk())
        .andReturn();
    String token = body(link).get("token").asText();
    assertThat(token).isNotBlank();

    MvcResult preview = mvc.perform(get("/api/auth/invitations/" + token))
        .andExpect(status().isOk())
        .andReturn();
    assertThat(body(preview).get("kind").asText()).isEqualTo("USER");
    assertThat(body(preview).get("email").asText()).isEqualTo(email);

    mvc.perform(post("/api/auth/invitations/accept")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("token", token, "password", "setup1234"))))
        .andExpect(status().isOk());

    mvc.perform(post("/api/auth/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("email", email, "password", "setup1234"))))
        .andExpect(status().isOk());

    mvc.perform(get("/api/auth/invitations/" + token))
        .andExpect(status().isUnauthorized());
  }

  /** 고를 것이 없다 — 누르면 링크가 나온다. */
  private JsonNode createInvite() throws Exception {
    MvcResult result = mvc.perform(post(invitesPath())
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isCreated())
        .andReturn();
    return body(result);
  }

  private String invitesPath() {
    return "/api/projects/" + SEED_PROJECT_ID + "/invites";
  }

  private String assignmentsPath() {
    return "/api/projects/" + SEED_PROJECT_ID + "/assignments";
  }
}
