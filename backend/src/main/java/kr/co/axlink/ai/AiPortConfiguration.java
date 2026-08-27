package kr.co.axlink.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.http.HttpClient;
import java.time.Duration;
import kr.co.axlink.ai.adapter.fake.FakeEmbeddingAdapter;
import kr.co.axlink.ai.adapter.fake.FakeLlmAdapter;
import kr.co.axlink.ai.adapter.ollama.OllamaEmbeddingAdapter;
import kr.co.axlink.ai.adapter.ollama.OllamaHttp;
import kr.co.axlink.ai.adapter.ollama.OllamaLlmAdapter;
import kr.co.axlink.ai.port.EmbeddingPort;
import kr.co.axlink.ai.port.LlmModels;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.config.AxLinkProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AiPortConfiguration {

  @Bean
  public LlmModels llmModels(AxLinkProperties properties) {
    AxLinkProperties.Model model = properties.ai().ollama().model();
    return new LlmModels(model.chat(), model.document(), model.embedding());
  }

  @Bean
  @ConditionalOnProperty(name = "axlink.ai.adapter", havingValue = "ollama", matchIfMissing = true)
  public OllamaHttp ollamaHttp(AxLinkProperties properties, ObjectMapper objectMapper) {
    HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    return new OllamaHttp(client, objectMapper, properties.ai().ollama());
  }

  @Bean
  @ConditionalOnProperty(name = "axlink.ai.adapter", havingValue = "ollama", matchIfMissing = true)
  public LlmPort ollamaLlmPort(OllamaHttp ollamaHttp) {
    return new OllamaLlmAdapter(ollamaHttp);
  }

  @Bean
  @ConditionalOnProperty(name = "axlink.ai.adapter", havingValue = "ollama", matchIfMissing = true)
  public EmbeddingPort ollamaEmbeddingPort(OllamaHttp ollamaHttp, AxLinkProperties properties) {
    return new OllamaEmbeddingAdapter(ollamaHttp, properties.ai().ollama());
  }

  @Bean
  @ConditionalOnProperty(name = "axlink.ai.adapter", havingValue = "fake")
  public LlmPort fakeLlmPort() {
    return new FakeLlmAdapter();
  }

  @Bean
  @ConditionalOnProperty(name = "axlink.ai.adapter", havingValue = "fake")
  public EmbeddingPort fakeEmbeddingPort() {
    return new FakeEmbeddingAdapter();
  }
}
