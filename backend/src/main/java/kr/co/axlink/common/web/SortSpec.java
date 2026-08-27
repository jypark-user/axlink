package kr.co.axlink.common.web;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import kr.co.axlink.common.error.ApiExceptions;

public final class SortSpec {

  private final String orderByClause;

  private SortSpec(String orderByClause) {
    this.orderByClause = orderByClause;
  }

  public static SortSpec parse(List<String> raw, Map<String, String> whitelist,
      String defaultClause) {
    if (raw == null || raw.isEmpty()) {
      return new SortSpec(defaultClause);
    }
    List<String> terms = new ArrayList<>();
    for (String entry : raw) {
      if (entry == null || entry.isBlank()) {
        continue;
      }
      String[] parts = entry.split(",");
      String field = parts[0].trim();
      String column = whitelist.get(field);
      if (column == null) {
        throw ApiExceptions.validationFailed("정렬할 수 없는 필드입니다: " + field);
      }
      String direction = parts.length > 1 ? parts[1].trim().toLowerCase() : "asc";
      if (!direction.equals("asc") && !direction.equals("desc")) {
        throw ApiExceptions.validationFailed("정렬 방향은 asc 또는 desc 여야 합니다: " + direction);
      }
      terms.add(column + " " + direction);
    }
    return new SortSpec(terms.isEmpty() ? defaultClause : String.join(", ", terms));
  }

  public String toOrderByClause() {
    return orderByClause;
  }

  @Override
  public String toString() {
    return orderByClause;
  }
}
