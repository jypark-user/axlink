package kr.co.axlink.semantic.service;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.semantic.domain.BoundFilter;
import kr.co.axlink.semantic.domain.FilterDef;
import kr.co.axlink.semantic.domain.FilterValueType;
import org.springframework.stereotype.Component;

@Component
public class FilterBinder {

  public record Fragment(String sql, Map<String, Object> params) {
  }

  public Fragment bind(FilterDef def, kr.co.axlink.dashboard.dto.WidgetFilter value,
      String timeColumn, int index) {
    String pName = ":p" + index;
    String column = resolveColumn(def, timeColumn);
    List<Object> values = extractValues(def, value);
    return switch (def.op()) {
      case IN -> new Fragment(column + " = any(" + pName + ")", bindIn(def, pName, values));
      case EQ -> new Fragment(column + " = " + pName, Map.of(pName.substring(1), cast(def, values.get(0))));
      case GTE -> new Fragment(column + " >= " + pName, Map.of(pName.substring(1), cast(def, values.get(0))));
      case LTE -> new Fragment(column + " <= " + pName, Map.of(pName.substring(1), cast(def, values.get(0))));
      case BETWEEN -> betweenFragment(def, column, pName, index, values);
      case IN_MONTH -> monthFragment(def, column, pName, values);
      case LAST_N_DAYS -> new Fragment(
          column + " >= now() - make_interval(days => " + pName + ")",
          Map.of(pName.substring(1), intValue(values.get(0))));
    };
  }

  private Fragment betweenFragment(FilterDef def, String column, String pName, int index,
      List<Object> values) {
    if (values.size() != 2) {
      throw ApiExceptions.validationFailed("BETWEEN 필터는 시작·종료 값 2개가 필요합니다.");
    }
    String p0 = "p" + index;
    String p1 = "p" + (index + 1);
    Map<String, Object> params = new LinkedHashMap<>();
    params.put(p0, asDate(values.get(0)));
    params.put(p1, asDate(values.get(1)));
    return new Fragment(column + " between :" + p0 + " and :" + p1, params);
  }

  private Fragment monthFragment(FilterDef def, String column, String pName, List<Object> values) {
    Object token = values.get(0);
    LocalDate date = "current".equalsIgnoreCase(String.valueOf(token))
        ? LocalDate.now()
        : LocalDate.parse(String.valueOf(token) + "-01");
    return new Fragment(
        "date_trunc('month', " + column + ") = date_trunc('month', " + pName + "::date)",
        Map.of(pName.substring(1), date));
  }

  private Map<String, Object> bindIn(FilterDef def, String pName, List<Object> values) {
    List<Object> casted = new ArrayList<>();
    for (Object v : values) {
      casted.add(cast(def, v));
    }
    return Map.of(pName.substring(1),
        def.valueType() == FilterValueType.UUID_LIST ? toUuidArray(casted) : casted.toArray(new String[0]));
  }

  private String resolveColumn(FilterDef def, String timeColumn) {
    return def.columnExpr().replace("<TIME_COL>", timeColumn);
  }

  private List<Object> extractValues(FilterDef def, kr.co.axlink.dashboard.dto.WidgetFilter value) {
    Object raw = value.value();
    if (raw instanceof List<?> list) {
      return list.stream().map(v -> (Object) v).toList();
    }
    return List.of(raw);
  }

  private Object cast(FilterDef def, Object v) {
    if (def.valueType() == FilterValueType.UUID_LIST && v instanceof String s) {
      try {
        return UUID.fromString(s);
      } catch (IllegalArgumentException e) {
        throw ApiExceptions.catalogValidationFailed("UUID 값이 올바르지 않습니다: " + s);
      }
    }
    if (def.valueType() == FilterValueType.ENUM_LIST) {
      String s = String.valueOf(v);
      if (!def.enumValues().contains(s)) {
        throw ApiExceptions.catalogValidationFailed(
            "enum 값이 허용 목록에 없습니다: " + s + " (field=" + def.field() + ")");
      }
      return s;
    }
    return v;
  }

  private UUID[] toUuidArray(List<Object> values) {
    return values.stream().map(v -> (UUID) v).toArray(UUID[]::new);
  }

  private int intValue(Object v) {
    if (v instanceof Number n) {
      return n.intValue();
    }
    try {
      return Integer.parseInt(String.valueOf(v));
    } catch (NumberFormatException e) {
      throw ApiExceptions.validationFailed("정수 값이 올바르지 않습니다: " + v);
    }
  }

  private LocalDate asDate(Object v) {
    if (v instanceof LocalDate d) {
      return d;
    }
    try {
      return LocalDate.parse(String.valueOf(v));
    } catch (Exception e) {
      throw ApiExceptions.validationFailed("날짜 값이 올바르지 않습니다: " + v);
    }
  }

  public BoundFilter bindValues(FilterDef def, kr.co.axlink.dashboard.dto.WidgetFilter value) {
    return new BoundFilter(def, extractValues(def, value));
  }
}
