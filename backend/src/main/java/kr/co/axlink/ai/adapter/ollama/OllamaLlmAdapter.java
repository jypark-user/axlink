package kr.co.axlink.ai.adapter.ollama;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Consumer;
import kr.co.axlink.ai.port.LlmDelta;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.ai.port.LlmResponse;
import kr.co.axlink.ai.port.ToolInvocation;
import kr.co.axlink.ai.port.ToolRequest;
import kr.co.axlink.common.error.ApiExceptions;

public class OllamaLlmAdapter implements LlmPort {

  private static final String CHAT_PATH = "/api/chat";

  private final OllamaHttp http;
  private final ObjectMapper objectMapper;

  public OllamaLlmAdapter(OllamaHttp http) {
    this.http = http;
    this.objectMapper = http.objectMapper();
  }

  @Override
  public LlmResponse complete(LlmRequest request) {
    OllamaWire.ChatChunk chunk = readSingle(body(request, false, null));
    String text = chunk.message() == null ? "" : nullToEmpty(chunk.message().content());
    return new LlmResponse(
        text,
        chunk.model(),
        chunk.promptEvalCount() == null ? 0 : chunk.promptEvalCount(),
        chunk.evalCount() == null ? 0 : chunk.evalCount());
  }

  @Override
  public void stream(LlmRequest request, Consumer<LlmDelta> onDelta) {
    HttpResponse<InputStream> response =
        http.post(CHAT_PATH, body(request, true, null), HttpResponse.BodyHandlers.ofInputStream());
    try (InputStream in = response.body();
        BufferedReader reader =
            new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        if (line.isBlank()) {
          continue;
        }
        OllamaWire.ChatChunk chunk = parseChunk(line);
        String text = chunk.message() == null ? "" : nullToEmpty(chunk.message().content());
        if (!text.isEmpty() || chunk.done()) {
          onDelta.accept(new LlmDelta(text, chunk.done()));
        }
        if (chunk.done()) {
          return;
        }
      }
      onDelta.accept(new LlmDelta("", true));
    } catch (IOException e) {
      throw ApiExceptions.aiUnavailable("Ollama stream failed: " + e);
    }
  }

  @Override
  public ToolInvocation callTool(ToolRequest request) {
    List<OllamaWire.ToolDef> tools =
        List.of(
            OllamaWire.ToolDef.function(
                request.tool().name(),
                request.tool().description(),
                request.tool().parameters()));
    OllamaWire.ChatChunk chunk = readSingle(body(request.base(), false, tools));
    OllamaWire.ChatMessage message = chunk.message();
    String rawText = message == null ? "" : nullToEmpty(message.content());
    if (message == null || message.tool_calls() == null || message.tool_calls().isEmpty()) {
      return new ToolInvocation(null, null, rawText);
    }
    OllamaWire.FunctionCall call = message.tool_calls().get(0).function();
    if (call == null || call.name() == null) {
      return new ToolInvocation(null, null, rawText);
    }
    return new ToolInvocation(call.name(), normalizeArguments(call.arguments()), rawText);
  }

  private JsonNode normalizeArguments(JsonNode arguments) {
    if (arguments == null || arguments.isNull()) {
      return objectMapper.createObjectNode();
    }
    if (arguments.isTextual()) {
      try {
        return objectMapper.readTree(arguments.textValue());
      } catch (IOException e) {
        return objectMapper.createObjectNode();
      }
    }
    return arguments;
  }

  private OllamaWire.ChatChunk readSingle(OllamaWire.ChatRequest request) {
    HttpResponse<String> response =
        http.post(CHAT_PATH, request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    List<OllamaWire.ChatChunk> chunks = new ArrayList<>();
    for (String line : response.body().split("\n")) {
      if (!line.isBlank()) {
        chunks.add(parseChunk(line));
      }
    }
    if (chunks.isEmpty()) {
      throw ApiExceptions.aiUnavailable("Ollama returned an empty response body");
    }
    return chunks.get(chunks.size() - 1);
  }

  private OllamaWire.ChatChunk parseChunk(String line) {
    try {
      OllamaWire.ChatChunk chunk = objectMapper.readValue(line, OllamaWire.ChatChunk.class);
      if (chunk.error() != null) {
        throw ApiExceptions.aiUnavailable("Ollama reported an error: " + chunk.error());
      }
      return chunk;
    } catch (IOException e) {
      throw ApiExceptions.aiUnavailable("Ollama returned malformed NDJSON" + " <- " + e);
    }
  }

  private static OllamaWire.ChatRequest body(
      LlmRequest request, boolean stream, List<OllamaWire.ToolDef> tools) {
    List<OllamaWire.ChatMessage> messages =
        request.messages().stream()
            .map(
                m ->
                    OllamaWire.ChatMessage.of(
                        m.role().name().toLowerCase(Locale.ROOT), m.content()))
            .toList();
    Map<String, Object> options = new LinkedHashMap<>();
    if (request.temperature() != null) {
      options.put("temperature", request.temperature());
    }
    if (request.maxTokens() != null) {
      options.put("num_predict", request.maxTokens());
    }
    return new OllamaWire.ChatRequest(
        request.model(),
        messages,
        stream,
        request.think(),
        tools,
        options.isEmpty() ? null : options);
  }

  private static String nullToEmpty(String value) {
    return value == null ? "" : value;
  }
}
