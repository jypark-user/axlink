package kr.co.axlink.ai;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import kr.co.axlink.ai.adapter.fake.FakeEmbeddingAdapter;
import kr.co.axlink.ai.adapter.fake.FakeLlmAdapter;
import kr.co.axlink.ai.port.LlmDelta;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.ai.port.ToolInvocation;
import kr.co.axlink.ai.port.ToolRequest;
import kr.co.axlink.ai.port.ToolSchema;
import org.junit.jupiter.api.Test;

class FakeAiAdapterTest {

  private final FakeEmbeddingAdapter embedding = new FakeEmbeddingAdapter();
  private final FakeLlmAdapter llm = new FakeLlmAdapter();

  @Test
  void embeddingIsDeterministicNormalizedAnd1024Dimensional() {
    assertEquals(1024, embedding.dimension());
    float[] first = embedding.embed(List.of("변경요청 현황")).get(0);
    float[] second = embedding.embed(List.of("변경요청 현황")).get(0);
    assertArrayEquals(first, second);
    assertEquals(1024, first.length);

    double sumOfSquares = 0.0;
    for (float value : first) {
      sumOfSquares += (double) value * value;
    }
    assertEquals(1.0, Math.sqrt(sumOfSquares), 1e-4);

    float[] other = embedding.embed(List.of("이슈 현황")).get(0);
    assertFalse(java.util.Arrays.equals(first, other));
  }

  @Test
  void separateAdapterInstancesProduceIdenticalOutput() {
    String text = "요구사항 이행률은 얼마인가";
    assertArrayEquals(
        new FakeEmbeddingAdapter().embed(List.of(text)).get(0),
        new FakeEmbeddingAdapter().embed(List.of(text)).get(0));
    LlmRequest request = LlmRequest.of("glm-5.2:cloud", List.of(LlmMessage.user(text)));
    assertEquals(
        new FakeLlmAdapter().complete(request).text(),
        new FakeLlmAdapter().complete(request).text());
  }

  @Test
  void embeddingHandlesBatchesLargerThanOneChunk() {
    List<String> texts = new ArrayList<>();
    for (int i = 0; i < 70; i++) {
      texts.add("chunk-" + i);
    }
    assertEquals(70, embedding.embed(texts).size());
  }

  @Test
  void streamEmitsSameTextAsCompleteAndEndsWithDone() {
    LlmRequest request =
        LlmRequest.of("glm-5.2:cloud", List.of(LlmMessage.user("변경요청은 몇 건인가")));
    StringBuilder streamed = new StringBuilder();
    List<LlmDelta> deltas = new ArrayList<>();
    llm.stream(
        request,
        delta -> {
          streamed.append(delta.text());
          deltas.add(delta);
        });
    assertEquals(llm.complete(request).text(), streamed.toString());
    assertTrue(deltas.get(deltas.size() - 1).done());
  }

  @Test
  void callToolReturnsSchemaConformingArguments() {
    ToolSchema schema =
        new ToolSchema(
            "classify_query",
            "분류",
            Map.of(
                "type",
                "object",
                "properties",
                Map.of(
                    "route", Map.of("type", "string", "enum", List.of("DOCUMENT", "AGGREGATE")),
                    "rewrittenQuery", Map.of("type", "string"))));
    ToolInvocation invocation =
        llm.callTool(
            new ToolRequest(
                LlmRequest.of("glm-5.2:cloud", List.of(LlmMessage.user("그거 몇 건이야"))), schema));

    assertTrue(invocation.isPresent());
    assertEquals("classify_query", invocation.toolName());
    JsonNode arguments = invocation.arguments();
    assertEquals("DOCUMENT", arguments.get("route").asText());
    assertEquals("fake-rewrittenQuery", arguments.get("rewrittenQuery").asText());
  }
}
