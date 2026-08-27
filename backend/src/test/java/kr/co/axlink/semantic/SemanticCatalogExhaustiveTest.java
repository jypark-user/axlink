package kr.co.axlink.semantic;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetFilter;
import kr.co.axlink.dashboard.dto.WidgetOptions;
import kr.co.axlink.dashboard.dto.WidgetQuery;
import kr.co.axlink.dashboard.dto.WidgetSpec;
import kr.co.axlink.semantic.domain.FilterDef;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.service.CatalogRegistry;
import kr.co.axlink.semantic.service.SemanticQueryBuilder;
import kr.co.axlink.semantic.service.WidgetSpecValidator;
import kr.co.axlink.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.simple.JdbcClient;

class SemanticCatalogExhaustiveTest extends AbstractIntegrationTest {

  private static final Set<UUID> SCOPE = Set.of(SEED_PROJECT_ID,
      UUID.fromString("c0000000-0000-4000-8000-0000000000ff"));

  @Autowired
  private CatalogRegistry registry;
  @Autowired
  private WidgetSpecValidator validator;
  @Autowired
  private SemanticQueryBuilder builder;
  @Autowired
  private JdbcClient jdbcClient;

  @Test
  void everyMeasureRunsAloneAndWithEachAllowedDimensionAndFilter() {
    List<String> failures = new ArrayList<>();
    int executed = 0;
    for (MeasureDef measure : registry.activeMeasures()) {
      List<String> dims = new ArrayList<>(measure.allowedDimensions());
      List<FilterDef> filters = allowedFilterDefs(measure);

      executed += run(failures, measure, List.of(), List.of());
      for (String dim : dims) {
        executed += run(failures, measure, List.of(dim), List.of());
      }
      for (FilterDef filter : filters) {
        executed += run(failures, measure, List.of(), List.of(sample(filter)));
      }
      for (String dim : dims) {
        for (FilterDef filter : filters) {
          executed += run(failures, measure, List.of(dim), List.of(sample(filter)));
        }
      }
      for (int i = 0; i < dims.size(); i++) {
        for (int j = i + 1; j < dims.size(); j++) {
          executed += run(failures, measure, List.of(dims.get(i), dims.get(j)), List.of());
        }
      }
    }
    assertThat(failures).isEmpty();
    assertThat(executed).isGreaterThan(400);
  }

  @Test
  void contractorOrgFilterRunsWithoutAnyDimension() {
    List<String> failures = new ArrayList<>();
    FilterDef def = registry.filter("contractor_org_id", kr.co.axlink.semantic.domain.FilterOp.IN)
        .orElseThrow();
    for (MeasureDef measure : registry.activeMeasures()) {
      if (!measure.allowedFilters().contains(def.key())) {
        continue;
      }
      run(failures, measure, List.of(), List.of(sample(def)));
    }
    assertThat(failures).isEmpty();
  }

  @Test
  void codeActivityCountGroupsByAuthorDimension() {
    List<String> failures = new ArrayList<>();
    MeasureDef measure = registry.measure("code_activity_count").orElseThrow();
    assertThat(measure.allowedDimensions()).contains("author");
    run(failures, measure, List.of("author"), List.of());
    assertThat(failures).isEmpty();
  }

  @Test
  void labelledDimensionsSelectAndGroupByBothExpressions() {
    List<String> failures = new ArrayList<>();
    for (String dim : List.of("project", "contractor_org")) {
      assertThat(registry.dimension(dim).orElseThrow().labelExpr()).isNotBlank();
    }
    MeasureDef measure = registry.measure("issue_resolution_rate").orElseThrow();
    SemanticQueryBuilder.BuiltQuery query = builder.build(
        validator.validate(spec(measure, List.of("project", "contractor_org"), List.of()), SCOPE));
    assertThat(query.sql()).contains("d0_label").contains("d1_label");
    assertThat(query.sql().substring(query.sql().indexOf(" group by ")))
        .contains("d0").contains("d0_label").contains("d1").contains("d1_label");
    run(failures, measure, List.of("project", "contractor_org"), List.of());
    assertThat(failures).isEmpty();
  }

  private List<FilterDef> allowedFilterDefs(MeasureDef measure) {
    List<FilterDef> defs = new ArrayList<>();
    for (FilterDef def : registry.activeFilters()) {
      if (measure.allowedFilters().contains(def.key())) {
        defs.add(def);
      }
    }
    return defs;
  }

  private int run(List<String> failures, MeasureDef measure, List<String> dimensions,
      List<WidgetFilter> filters) {
    String label = measure.key() + " dims=" + dimensions
        + " filters=" + filters.stream().map(WidgetFilter::field).toList();
    try {
      SemanticQueryBuilder.BuiltQuery query =
          builder.build(validator.validate(spec(measure, dimensions, filters), SCOPE));
      jdbcClient.sql(query.sql()).params(query.params()).query().listOfRows();
    } catch (RuntimeException e) {
      failures.add(label + " -> " + e.getClass().getSimpleName() + ": " + rootMessage(e));
    }
    return 1;
  }

  private WidgetSpec spec(MeasureDef measure, List<String> dimensions, List<WidgetFilter> filters) {
    return new WidgetSpec(WidgetTemplate.DATA_TABLE, measure.label(),
        new WidgetQuery(measure.key(), dimensions, filters, List.copyOf(SCOPE), 20),
        new WidgetOptions(null, "desc", null, null, null, null, null));
  }

  private WidgetFilter sample(FilterDef def) {
    Object value = switch (def.valueType()) {
      case UUID_LIST -> List.of(SEED_PROJECT_ID.toString(), SEED_CONTRACTOR_ORG_ID.toString());
      case ENUM_LIST -> List.copyOf(def.enumValues()).subList(0, 1);
      case DATE_RANGE -> List.of("2026-01-01", "2026-12-31");
      case MONTH_TOKEN -> "current";
      case INT -> 30;
    };
    return new WidgetFilter(def.field(), def.op().name(), value);
  }

  private String rootMessage(Throwable e) {
    Throwable cursor = e;
    while (cursor.getCause() != null) {
      cursor = cursor.getCause();
    }
    return String.valueOf(cursor.getMessage()).replace('\n', ' ');
  }
}
