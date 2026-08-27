package kr.co.axlink.semantic.service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.dashboard.dto.WidgetDataRequest;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetFilter;
import kr.co.axlink.dashboard.dto.WidgetSpec;
import kr.co.axlink.semantic.domain.AggregateContext;
import kr.co.axlink.semantic.domain.ValidatedSpec;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class SemanticQueryExecutor {

  private final JdbcClient jdbcClient;
  private final WidgetSpecValidator validator;
  private final SemanticQueryBuilder builder;
  private final WidgetDataAssembler assembler;

  public SemanticQueryExecutor(JdbcClient jdbcClient, WidgetSpecValidator validator,
      SemanticQueryBuilder builder, WidgetDataAssembler assembler) {
    this.jdbcClient = jdbcClient;
    this.validator = validator;
    this.builder = builder;
    this.assembler = assembler;
  }

  public WidgetDataResponse run(WidgetSpec spec, AuthPrincipal principal,
      WidgetDataRequest override) {
    WidgetSpec effective = applyOverride(spec, override);
    ValidatedSpec validated = validator.validate(effective, principal);
    SemanticQueryBuilder.BuiltQuery query = builder.build(validated);
    List<Map<String, Object>> rows = runQuery(query);
    boolean truncated = rows.size() >= validated.limit();
    WidgetDataResponse previous = null;
    if (shouldCompare(validated)) {
      ValidatedSpec previousSpec = shiftPeriodWindow(validated);
      if (previousSpec != null) {
        SemanticQueryBuilder.BuiltQuery prevQuery = builder.build(previousSpec);
        List<Map<String, Object>> prevRows = runQuery(prevQuery);
        previous = assembler.assemblePrevious(previousSpec, prevRows);
      }
    }
    return assembler.assemble(validated, rows, truncated, previous);
  }

  public AggregateContext runForRag(String measureKey, List<String> dimensions,
      List<WidgetFilter> filters, Set<UUID> allowedProjectIds) {
    kr.co.axlink.dashboard.dto.WidgetQuery query = new kr.co.axlink.dashboard.dto.WidgetQuery(
        measureKey, dimensions, filters, List.copyOf(allowedProjectIds), 50);
    kr.co.axlink.dashboard.dto.WidgetSpec spec = new kr.co.axlink.dashboard.dto.WidgetSpec(
        kr.co.axlink.dashboard.domain.WidgetTemplate.DATA_TABLE, measureKey, query,
        new kr.co.axlink.dashboard.dto.WidgetOptions(null, null, null, null, null, null, null));
    ValidatedSpec validated = validator.validate(spec, allowedProjectIds);
    SemanticQueryBuilder.BuiltQuery built = builder.build(validated);
    List<Map<String, Object>> rows = runQuery(built);
    return new AggregateContext(measureKey, dimensions, rows, validated.projectIds(),
        assembler.assemble(validated, rows, false, null));
  }

  private List<Map<String, Object>> runQuery(SemanticQueryBuilder.BuiltQuery query) {
    return jdbcClient.sql(query.sql()).params(query.params())
        .query((rs, rowNum) -> {
          Map<String, Object> row = new LinkedHashMap<>();
          int n = rs.getMetaData().getColumnCount();
          for (int c = 1; c <= n; c++) {
            row.put(rs.getMetaData().getColumnLabel(c), rs.getObject(c));
          }
          return row;
        }).list();
  }

  private boolean shouldCompare(ValidatedSpec spec) {
    Boolean flag = spec.options().compareWithPrevious();
    return flag != null && flag && spec.dimensions().isEmpty();
  }

  private ValidatedSpec shiftPeriodWindow(ValidatedSpec spec) {
    // ponytail: 단순 이전 기간 산출은 period__last_n_days / period__between 한정. 복잡 일정 산출은 추후.
    return null;
  }

  private WidgetSpec applyOverride(WidgetSpec spec, WidgetDataRequest override) {
    if (override == null) {
      return spec;
    }
    WidgetSpec current = spec;
    if (override.projectScopeOverride() != null && !override.projectScopeOverride().isEmpty()) {
      kr.co.axlink.dashboard.dto.WidgetQuery q = current.query();
      current = new WidgetSpec(current.template(), current.title(),
          new kr.co.axlink.dashboard.dto.WidgetQuery(q.measure(), q.dimensions(),
              q.filters(), override.projectScopeOverride(), q.limit()),
          current.options());
    }
    if (override.periodOverride() != null) {
      kr.co.axlink.dashboard.dto.WidgetQuery q = current.query();
      List<WidgetFilter> filters = new java.util.ArrayList<>(q.filters() == null
          ? List.of() : q.filters());
      filters.removeIf(f -> "period".equals(f.field()));
      filters.add(override.periodOverride());
      current = new WidgetSpec(current.template(), current.title(),
          new kr.co.axlink.dashboard.dto.WidgetQuery(q.measure(), q.dimensions(),
              filters, q.projectScope(), q.limit()),
          current.options());
    }
    return current;
  }
}
