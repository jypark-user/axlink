package kr.co.axlink.dashboard.dto;

import java.util.List;

public record WidgetFilter(
    String field,
    String op,
    Object value) {

  public List<Object> valueAsList() {
    if (value instanceof List<?> list) {
      return list.stream().map(v -> (Object) v).toList();
    }
    return List.of(value);
  }
}
