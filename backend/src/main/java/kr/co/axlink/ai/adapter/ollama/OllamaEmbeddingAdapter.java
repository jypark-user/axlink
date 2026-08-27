package kr.co.axlink.ai.adapter.ollama;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import kr.co.axlink.ai.port.EmbeddingPort;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.config.AxLinkProperties;

public class OllamaEmbeddingAdapter implements EmbeddingPort {

  private static final String EMBED_PATH = "/api/embed";
  private static final int BATCH_SIZE = 32;

  private final OllamaHttp http;
  private final ObjectMapper objectMapper;
  private final String model;
  private final int dimension;

  public OllamaEmbeddingAdapter(OllamaHttp http, AxLinkProperties.Ollama properties) {
    this.http = http;
    this.objectMapper = http.objectMapper();
    this.model = properties.model().embedding();
    this.dimension = properties.embeddingDimension();
  }

  @Override
  public List<float[]> embed(List<String> texts) {
    List<float[]> result = new ArrayList<>(texts.size());
    for (int from = 0; from < texts.size(); from += BATCH_SIZE) {
      int to = Math.min(from + BATCH_SIZE, texts.size());
      result.addAll(embedBatch(texts.subList(from, to)));
    }
    return result;
  }

  @Override
  public int dimension() {
    return dimension;
  }

  private List<float[]> embedBatch(List<String> batch) {
    HttpResponse<String> response =
        http.post(
            EMBED_PATH,
            new OllamaWire.EmbedRequest(model, batch),
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    OllamaWire.EmbedResponse parsed = parse(response.body());
    if (parsed.error() != null) {
      throw ApiExceptions.aiUnavailable("Ollama reported an error: " + parsed.error());
    }
    if (parsed.embeddings() == null || parsed.embeddings().size() != batch.size()) {
      throw ApiExceptions.aiUnavailable(
          "Ollama returned " + count(parsed) + " embeddings for " + batch.size() + " inputs");
    }
    List<float[]> vectors = new ArrayList<>(batch.size());
    for (List<Float> embedding : parsed.embeddings()) {
      if (embedding.size() != dimension) {
        throw ApiExceptions.aiUnavailable(
            "Ollama embedding dimension " + embedding.size() + " != expected " + dimension);
      }
      float[] vector = new float[dimension];
      for (int i = 0; i < dimension; i++) {
        vector[i] = embedding.get(i);
      }
      vectors.add(vector);
    }
    return vectors;
  }

  private OllamaWire.EmbedResponse parse(String body) {
    try {
      return objectMapper.readValue(body, OllamaWire.EmbedResponse.class);
    } catch (IOException e) {
      throw ApiExceptions.aiUnavailable("Ollama returned a malformed embed response" + " <- " + e);
    }
  }

  private static int count(OllamaWire.EmbedResponse parsed) {
    return parsed.embeddings() == null ? 0 : parsed.embeddings().size();
  }
}
