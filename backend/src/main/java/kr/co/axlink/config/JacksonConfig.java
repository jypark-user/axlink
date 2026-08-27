package kr.co.axlink.config;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import java.util.TimeZone;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonConfig {

  @Bean
  public Jackson2ObjectMapperBuilderCustomizer axLinkJacksonCustomizer() {
    return builder -> builder
        .timeZone(TimeZone.getTimeZone("UTC"))
        .featuresToDisable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS,
            SerializationFeature.FAIL_ON_EMPTY_BEANS)
        .featuresToEnable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
  }
}
