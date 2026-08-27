package kr.co.axlink.support;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@AutoConfigureMockMvc
public abstract class AbstractHttpFlowTest extends AbstractIntegrationTest {

  protected static final String CLIENT_EMAIL = "r2@admin.com";
  protected static final String CONTRACTOR_EMAIL = "r3@admin.com";
  protected static final String ADMIN_EMAIL = "r1@admin.com";
  protected static final String SEED_PASSWORD = "admin";

  @Autowired
  protected MockMvc mvc;

  @Autowired
  protected ObjectMapper objectMapper;

  protected String loginAs(String email) throws Exception {
    MvcResult result = mvc.perform(post("/api/auth/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content(json(Map.of("email", email, "password", SEED_PASSWORD))))
        .andExpect(status().isOk())
        .andReturn();
    JsonNode token = body(result).get("accessToken");
    if (token == null || token.asText().isBlank()) {
      throw new IllegalStateException("login for " + email + " returned no accessToken: "
          + text(result));
    }
    return "Bearer " + token.asText();
  }

  protected String json(Object value) {
    try {
      return objectMapper.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalStateException("failed to serialize test payload", e);
    }
  }

  protected JsonNode body(MvcResult result) {
    try {
      return objectMapper.readTree(text(result));
    } catch (Exception e) {
      throw new IllegalStateException("response was not json: " + safeText(result), e);
    }
  }

  protected String text(MvcResult result) {
    try {
      return result.getResponse().getContentAsString(StandardCharsets.UTF_8);
    } catch (Exception e) {
      throw new IllegalStateException("failed to read response body", e);
    }
  }

  private String safeText(MvcResult result) {
    try {
      return result.getResponse().getContentAsString(StandardCharsets.UTF_8);
    } catch (Exception e) {
      return "<unreadable>";
    }
  }
}
