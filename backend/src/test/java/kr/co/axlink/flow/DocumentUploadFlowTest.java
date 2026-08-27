package kr.co.axlink.flow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.support.AbstractHttpFlowTest;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;

class DocumentUploadFlowTest extends AbstractHttpFlowTest {

  private static final Set<String> TERMINAL =
      Set.of("EXTRACTED", "STRUCTURED", "CONFIRMED", "FAILED");
  private static final long POLL_TIMEOUT_MILLIS = 30_000L;

  private String clientToken;
  private final List<UUID> uploaded = new ArrayList<>();

  @BeforeEach
  void loginAsClient() throws Exception {
    clientToken = loginAs(CLIENT_EMAIL);
  }

  @AfterEach
  void removeUploadedDocuments() throws Exception {
    for (UUID documentId : uploaded) {
      mvc.perform(delete("/api/documents/" + documentId)
          .header(HttpHeaders.AUTHORIZATION, clientToken));
    }
    uploaded.clear();
  }

  @Test
  void uploadedDocumentProgressesThroughPipelineInsteadOfFailing() throws Exception {
    String marker = "AXLINK-E2E-" + UUID.randomUUID();
    MockMultipartFile file = new MockMultipartFile("file", marker + ".pdf",
        "application/pdf", pdfContaining(marker));

    MvcResult accepted = mvc.perform(multipart("/api/projects/" + SEED_PROJECT_ID + "/documents")
        .file(file)
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isAccepted())
        .andReturn();
    JsonNode body = body(accepted);
    UUID documentId = UUID.fromString(body.get("id").asText());
    uploaded.add(documentId);
    assertThat(body.get("status").asText())
        .as("업로드 직후 상태는 UPLOADED 여야 한다: %s", text(accepted))
        .isEqualTo("UPLOADED");
    assertThat(body.get("fileName").asText()).isEqualTo(marker + ".pdf");

    JsonNode settled = awaitTerminalStatus(documentId);
    assertThat(settled.get("status").asText())
        .as("업로드 파이프라인이 FAILED 로 끝나면 안 된다. error=%s",
            settled.get("error").asText(null))
        .isNotEqualTo("FAILED");
    assertThat(settled.get("error").asText(null))
        .as("정상 처리된 문서에는 오류가 없어야 한다: %s", settled)
        .isNull();
    assertThat(settled.get("extractedCharCount").asInt())
        .as("텍스트가 추출되어야 한다: %s", settled)
        .isGreaterThan(0);
  }

  @Test
  void uploadedDocumentAppearsInProjectDocumentList() throws Exception {
    String marker = "AXLINK-E2E-" + UUID.randomUUID();
    MockMultipartFile file = new MockMultipartFile("file", marker + ".pdf",
        "application/pdf", pdfContaining(marker));

    MvcResult accepted = mvc.perform(multipart("/api/projects/" + SEED_PROJECT_ID + "/documents")
        .file(file)
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isAccepted())
        .andReturn();
    UUID documentId = UUID.fromString(body(accepted).get("id").asText());
    uploaded.add(documentId);

    MvcResult listed = mvc.perform(get("/api/projects/" + SEED_PROJECT_ID + "/documents")
        .header(HttpHeaders.AUTHORIZATION, clientToken)
        .param("size", "100"))
        .andExpect(status().isOk())
        .andReturn();
    List<String> ids = new ArrayList<>();
    body(listed).get("content").forEach(node -> ids.add(node.get("id").asText()));
    assertThat(ids)
        .as("업로드한 문서가 프로젝트 자료 목록에 나타나야 한다: %s", text(listed))
        .contains(documentId.toString());
  }

  @Test
  void duplicateUploadOfSameContentIsRejected() throws Exception {
    String marker = "AXLINK-E2E-" + UUID.randomUUID();
    byte[] content = pdfContaining(marker);

    MvcResult first = mvc.perform(multipart("/api/projects/" + SEED_PROJECT_ID + "/documents")
        .file(new MockMultipartFile("file", marker + ".pdf", "application/pdf", content))
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isAccepted())
        .andReturn();
    uploaded.add(UUID.fromString(body(first).get("id").asText()));

    MvcResult second = mvc.perform(multipart("/api/projects/" + SEED_PROJECT_ID + "/documents")
        .file(new MockMultipartFile("file", marker + "-copy.pdf", "application/pdf", content))
        .header(HttpHeaders.AUTHORIZATION, clientToken))
        .andExpect(status().isConflict())
        .andReturn();
    assertThat(body(second).get("code").asText())
        .as("같은 내용의 재업로드는 DUPLICATE_RESOURCE 여야 한다: %s", text(second))
        .isEqualTo("DUPLICATE_RESOURCE");
  }

  private JsonNode awaitTerminalStatus(UUID documentId) throws Exception {
    long deadline = System.currentTimeMillis() + POLL_TIMEOUT_MILLIS;
    JsonNode last = null;
    while (System.currentTimeMillis() < deadline) {
      MvcResult result = mvc.perform(get("/api/documents/" + documentId)
          .header(HttpHeaders.AUTHORIZATION, clientToken))
          .andExpect(status().isOk())
          .andReturn();
      last = body(result);
      if (TERMINAL.contains(last.get("status").asText())) {
        return last;
      }
      Thread.sleep(200L);
    }
    throw new AssertionError("문서 " + documentId + " 가 " + POLL_TIMEOUT_MILLIS
        + "ms 안에 파이프라인을 끝내지 못했다: " + last);
  }

  private static byte[] pdfContaining(String text) throws Exception {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    try (PDDocument document = new PDDocument()) {
      PDPage page = new PDPage();
      document.addPage(page);
      try (PDPageContentStream content = new PDPageContentStream(document, page)) {
        content.beginText();
        content.setFont(PDType1Font.HELVETICA, 12);
        content.newLineAtOffset(72, 720);
        content.showText(text);
        content.endText();
      }
      document.save(out);
    }
    return out.toByteArray();
  }
}
