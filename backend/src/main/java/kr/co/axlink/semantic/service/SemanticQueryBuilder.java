package kr.co.axlink.semantic.service;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.co.axlink.semantic.domain.BoundFilter;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.FilterOp;
import kr.co.axlink.semantic.domain.FilterValueType;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.domain.ValidatedSpec;
import kr.co.axlink.semantic.dto.WidgetColumn;
import org.springframework.stereotype.Component;

@Component
public class SemanticQueryBuilder {

  public record BuiltQuery(
      String sql,
      Map<String, Object> params,
      List<WidgetColumn> columns) {
  }

  private static final Pattern JOIN_START = Pattern.compile(
      "(?i)\\b(?:left\\s+outer\\s+|right\\s+outer\\s+|full\\s+outer\\s+|left\\s+|right\\s+"
          + "|full\\s+|inner\\s+|cross\\s+)?join\\b");

  public BuiltQuery build(ValidatedSpec spec) {
    MeasureDef measure = spec.measure();
    String timeColumn = TimeColumns.of(measure.baseTable());

    Map<String, String> joins = new LinkedHashMap<>();
    addJoins(joins, measure.joinClause());
    for (DimensionDef d : spec.dimensions()) {
      addJoins(joins, d.requiresJoin());
    }
    for (BoundFilter bf : spec.filters()) {
      addJoins(joins, bf.def().requiresJoin());
    }

    StringBuilder select = new StringBuilder();
    List<WidgetColumn> columns = new ArrayList<>();
    List<String> groupBy = new ArrayList<>();
    int dimIndex = 0;
    for (DimensionDef d : spec.dimensions()) {
      String alias = "d" + dimIndex;
      String selectExpr = d.selectExpr().replace("<TIME_COL>", timeColumn);
      select.append(", ").append(selectExpr).append(" AS ").append(alias);
      columns.add(WidgetColumn.of(alias, d.label(),
          d.valueType() == kr.co.axlink.semantic.domain.DimensionValueType.TIME ? "date" : "string"));
      groupBy.add(alias);
      if (d.labelExpr() != null && !d.labelExpr().isBlank()) {
        String labelAlias = alias + "_label";
        select.append(", ").append(d.labelExpr()).append(" AS ").append(labelAlias);
        groupBy.add(labelAlias);
      }
      dimIndex++;
    }
    select.append(", ").append(measure.valueExpr()).append(" AS value");
    columns.add(WidgetColumn.of("value", measure.label(), valueColumnType(measure)));

    Map<String, Object> params = new LinkedHashMap<>();
    List<String> whereFragments = new ArrayList<>();
    whereFragments.add("e.project_id = any(:allowedProjectIds)");
    params.put("allowedProjectIds", spec.projectIds().toArray(new UUID[0]));

    if (measure.rowFilter() != null && !measure.rowFilter().isBlank()) {
      whereFragments.add(measure.rowFilter());
    }

    int paramIdx = 0;
    for (BoundFilter bf : spec.filters()) {
      FilterBinder.Fragment frag = bindFilter(bf.def(), bf.values(), timeColumn, paramIdx);
      whereFragments.add("(" + frag.sql() + ")");
      params.putAll(frag.params());
      paramIdx += countParams(bf.def(), frag.params());
    }

    StringBuilder sql = new StringBuilder("select ");
    sql.append(select.substring(2));
    sql.append(" from ").append(measure.baseTable()).append(" e");
    for (String join : joins.values()) {
      sql.append(' ').append(join);
    }
    sql.append(" where ").append(String.join(" and ", whereFragments));
    if (!groupBy.isEmpty()) {
      sql.append(" group by ").append(String.join(", ", groupBy));
    }
    // 시계열 차트는 값이 아니라 시간 순으로 읽어야 한다.
    // ponytail: limit 은 정렬 뒤에 걸리므로 데이터가 limit 을 넘으면 오래된 구간부터 잘린다.
    //           최근 N구간이 필요해지면 서브쿼리(desc limit → asc)로 감싼다.
    String timeAlias = timeDimensionAlias(spec);
    if (timeAlias != null) {
      sql.append(" order by ").append(timeAlias).append(" ASC");
    } else {
      String sort = spec.options().sort();
      sql.append(" order by value ").append("desc".equalsIgnoreCase(sort) ? "DESC" : "ASC");
    }
    sql.append(" limit :limit");
    params.put("limit", spec.limit());

    return new BuiltQuery(sql.toString(), params, columns);
  }

  private String timeDimensionAlias(ValidatedSpec spec) {
    List<DimensionDef> dims = spec.dimensions();
    for (int i = 0; i < dims.size(); i++) {
      if (dims.get(i).valueType() == kr.co.axlink.semantic.domain.DimensionValueType.TIME) {
        return "d" + i;
      }
    }
    return null;
  }

  private void addJoins(Map<String, String> joins, String clause) {
    if (clause == null || clause.isBlank()) {
      return;
    }
    Matcher matcher = JOIN_START.matcher(clause);
    List<Integer> starts = new ArrayList<>();
    while (matcher.find()) {
      starts.add(matcher.start());
    }
    if (starts.isEmpty()) {
      throw new IllegalStateException("join 절을 해석할 수 없습니다: " + clause);
    }
    for (int i = 0; i < starts.size(); i++) {
      int end = i + 1 < starts.size() ? starts.get(i + 1) : clause.length();
      String fragment = clause.substring(starts.get(i), end).trim();
      joins.putIfAbsent(joinAlias(fragment), fragment);
    }
  }

  private String joinAlias(String fragment) {
    Matcher matcher = JOIN_START.matcher(fragment);
    if (!matcher.find()) {
      throw new IllegalStateException("join 절을 해석할 수 없습니다: " + fragment);
    }
    String[] tokens = fragment.substring(matcher.end()).trim().split("\\s+");
    if (tokens.length == 0 || tokens[0].isEmpty()) {
      throw new IllegalStateException("join 대상 테이블을 찾을 수 없습니다: " + fragment);
    }
    String table = tokens[0];
    if (tokens.length == 1) {
      return unqualified(table);
    }
    String next = tokens[1];
    if ("on".equalsIgnoreCase(next) || "using".equalsIgnoreCase(next)
        || next.startsWith("(")) {
      return unqualified(table);
    }
    return "as".equalsIgnoreCase(next) && tokens.length > 2 ? tokens[2] : next;
  }

  private String unqualified(String table) {
    int dot = table.lastIndexOf('.');
    return dot < 0 ? table : table.substring(dot + 1);
  }

  private FilterBinder.Fragment bindFilter(kr.co.axlink.semantic.domain.FilterDef def,
      List<Object> values, String timeColumn, int index) {
    String pName = ":p" + index;
    String column = def.columnExpr().replace("<TIME_COL>", timeColumn);
    return switch (def.op()) {
      case IN -> new FilterBinder.Fragment(
          column + " = any(" + pName + ")",
          Map.of("p" + index, bindIn(def, values)));
      case EQ -> new FilterBinder.Fragment(
          column + " = " + pName, Map.of("p" + index, castScalar(def, values.get(0))));
      case GTE -> new FilterBinder.Fragment(
          column + " >= " + pName, Map.of("p" + index, castScalar(def, values.get(0))));
      case LTE -> new FilterBinder.Fragment(
          column + " <= " + pName, Map.of("p" + index, castScalar(def, values.get(0))));
      case BETWEEN -> betweenFragment(def, column, index, values);
      case IN_MONTH -> monthFragment(def, column, index, values);
      case LAST_N_DAYS -> new FilterBinder.Fragment(
          column + " >= now() - make_interval(days => " + pName + ")",
          Map.of("p" + index, intValue(values.get(0))));
    };
  }

  private FilterBinder.Fragment betweenFragment(kr.co.axlink.semantic.domain.FilterDef def,
      String column, int index, List<Object> values) {
    if (values.size() != 2) {
      throw kr.co.axlink.common.error.ApiExceptions.validationFailed(
          "BETWEEN 필터는 시작·종료 값 2개가 필요합니다.");
    }
    String p0 = "p" + index;
    String p1 = "p" + (index + 1);
    Map<String, Object> params = new LinkedHashMap<>();
    params.put(p0, asDate(values.get(0)));
    params.put(p1, asDate(values.get(1)));
    return new FilterBinder.Fragment(column + " between :" + p0 + " and :" + p1, params);
  }

  private FilterBinder.Fragment monthFragment(kr.co.axlink.semantic.domain.FilterDef def,
      String column, int index, List<Object> values) {
    Object token = values.get(0);
    LocalDate date = "current".equalsIgnoreCase(String.valueOf(token))
        ? LocalDate.now()
        : LocalDate.parse(String.valueOf(token) + "-01");
    return new FilterBinder.Fragment(
        "date_trunc('month', " + column + ") = date_trunc('month', :p" + index + "::date)",
        Map.of("p" + index, date));
  }

  private Object bindIn(kr.co.axlink.semantic.domain.FilterDef def, List<Object> values) {
    List<Object> casted = new ArrayList<>();
    for (Object v : values) {
      casted.add(castScalar(def, v));
    }
    return def.valueType() == FilterValueType.UUID_LIST
        ? casted.stream().map(v -> (UUID) v).toArray(UUID[]::new)
        : casted.toArray(new String[0]);
  }

  private Object castScalar(kr.co.axlink.semantic.domain.FilterDef def, Object v) {
    if (def.valueType() == FilterValueType.UUID_LIST && v instanceof String s) {
      try {
        return UUID.fromString(s);
      } catch (IllegalArgumentException e) {
        throw kr.co.axlink.common.error.ApiExceptions.catalogValidationFailed(
            "UUID 값이 올바르지 않습니다: " + s);
      }
    }
    if (def.valueType() == FilterValueType.ENUM_LIST) {
      String s = String.valueOf(v);
      if (!def.enumValues().contains(s)) {
        throw kr.co.axlink.common.error.ApiExceptions.catalogValidationFailed(
            "enum 값이 허용 목록에 없습니다: " + s);
      }
      return s;
    }
    return v;
  }

  private int intValue(Object v) {
    if (v instanceof Number n) {
      return n.intValue();
    }
    try {
      return Integer.parseInt(String.valueOf(v));
    } catch (NumberFormatException e) {
      throw kr.co.axlink.common.error.ApiExceptions.validationFailed("정수 값이 올바르지 않습니다: " + v);
    }
  }

  private LocalDate asDate(Object v) {
    if (v instanceof LocalDate d) {
      return d;
    }
    try {
      return LocalDate.parse(String.valueOf(v));
    } catch (Exception e) {
      throw kr.co.axlink.common.error.ApiExceptions.validationFailed("날짜 값이 올바르지 않습니다: " + v);
    }
  }

  private int countParams(kr.co.axlink.semantic.domain.FilterDef def, Map<String, Object> params) {
    return def.op() == FilterOp.BETWEEN ? 2 : 1;
  }

  private String valueColumnType(MeasureDef measure) {
    return switch (measure.valueType()) {
      case RATE_PCT, PCT_POINT -> "percent";
      case DAYS -> "number";
      case COUNT -> "number";
    };
  }
}
