package kr.co.axlink.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties("axlink")
public record AxLinkProperties(@DefaultValue Ai ai, @DefaultValue Sync sync,
    @DefaultValue Rag rag, @DefaultValue Storage storage) {

  public record Ai(@DefaultValue("ollama") String adapter, @DefaultValue Ollama ollama) {
  }

  public record Ollama(
      @DefaultValue("http://localhost:11434") String baseUrl,
      @DefaultValue("180") int timeoutSeconds,
      @DefaultValue Model model,
      @DefaultValue("1024") int embeddingDimension) {
  }

  public record Model(
      @DefaultValue("qwen3.5:cloud") String chat,
      @DefaultValue("qwen3.5:cloud") String document,
      @DefaultValue("bge-m3") String embedding) {
  }

  public record Sync(
      @DefaultValue("900000") long pollIntervalMs,
      @DefaultValue("1000") long backoffInitialMs,
      @DefaultValue("60000") long backoffMaxMs) {
  }

  public record Rag(
      @DefaultValue("800") int chunkTokens,
      @DefaultValue("0.15") double chunkOverlapRatio,
      @DefaultValue("40") int vectorTopK,
      @DefaultValue("40") int fulltextTopK,
      @DefaultValue("8") int fusedTopK) {
  }

  public record Storage(
      @DefaultValue("./axlink-storage") String root,
      @DefaultValue("52428800") long maxUploadBytes) {
  }
}
