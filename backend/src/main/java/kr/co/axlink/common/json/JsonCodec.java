package kr.co.axlink.common.json;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import kr.co.axlink.common.error.ApiExceptions;
import org.springframework.stereotype.Component;

@Component
public class JsonCodec {

  private final ObjectMapper objectMapper;

  public JsonCodec(ObjectMapper objectMapper) {
    this.objectMapper = objectMapper;
  }

  public <T> T read(String json, Class<T> type) {
    if (json == null) {
      return null;
    }
    try {
      return objectMapper.readValue(json, type);
    } catch (Exception e) {
      throw ApiExceptions.validationFailed("JSON 형식이 올바르지 않습니다: " + e.getMessage());
    }
  }

  public <T> T read(String json, TypeReference<T> type) {
    if (json == null) {
      return null;
    }
    try {
      return objectMapper.readValue(json, type);
    } catch (Exception e) {
      throw ApiExceptions.validationFailed("JSON 형식이 올바르지 않습니다: " + e.getMessage());
    }
  }

  public String write(Object value) {
    if (value == null) {
      return null;
    }
    try {
      return objectMapper.writeValueAsString(value);
    } catch (Exception e) {
      throw ApiExceptions.internal("JSON 직렬화에 실패했습니다.");
    }
  }

  public JsonNode tree(String json) {
    if (json == null) {
      return null;
    }
    try {
      return objectMapper.readTree(json);
    } catch (Exception e) {
      throw ApiExceptions.validationFailed("JSON 형식이 올바르지 않습니다.");
    }
  }
}
