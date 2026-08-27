package kr.co.axlink.semantic.service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetRow;
import kr.co.axlink.semantic.domain.DimensionValueType;
import kr.co.axlink.semantic.domain.ValidatedSpec;
import kr.co.axlink.semantic.dto.WidgetColumn;
import org.springframework.stereotype.Component;

@Component
public class WidgetDataAssembler {

  public WidgetDataResponse assemble(ValidatedSpec spec, List<Map<String, Object>> rows,
      boolean truncated, WidgetDataResponse previous) {
    List<String> dimKeys = spec.dimensions().stream().map(d -> d.key()).toList();
    List<WidgetColumn> columns = buildColumns(spec);
    List<WidgetRow> widgetRows = toRows(rows, spec);
    WidgetRow total = buildTotal(spec, rows);
    return new WidgetDataResponse(
        spec.measure().key(),
        spec.measure().label(),
        unit(spec),
        dimKeys,
        columns,
        widgetRows,
        total,
        previous == null ? null : previous.total(),
        spec.measure().targetValue(),
        List.copyOf(spec.projectIds()),
        truncated,
        Instant.now());
  }

  public WidgetDataResponse assemblePrevious(ValidatedSpec spec, List<Map<String, Object>> rows) {
    return assemble(spec, rows, false, null);
  }

  private List<WidgetColumn> buildColumns(ValidatedSpec spec) {
    List<WidgetColumn> cols = new ArrayList<>();
    int idx = 0;
    for (var d : spec.dimensions()) {
      cols.add(WidgetColumn.of(
          "d" + idx,
          d.label(),
          d.valueType() == DimensionValueType.TIME ? "date" : "string"));
      if (d.labelExpr() != null && !d.labelExpr().isBlank()) {
        cols.add(WidgetColumn.of("d" + idx + "_label", d.label() + " 명", "string"));
      }
      idx++;
    }
    cols.add(WidgetColumn.of("value", spec.measure().label(), valueColumnType(spec)));
    if (spec.template() == WidgetTemplate.PROGRESS_LIST) {
      // unit column handled by unit field
    }
    return cols;
  }

  private List<WidgetRow> toRows(List<Map<String, Object>> rows, ValidatedSpec spec) {
    List<WidgetRow> out = new ArrayList<>();
    List<String> whitelist = spec.options().columns();
    for (Map<String, Object> row : rows) {
      Map<String, Object> filtered = new LinkedHashMap<>(row);
      if (whitelist != null && !whitelist.isEmpty()
          && spec.template() == WidgetTemplate.DATA_TABLE) {
        filtered.keySet().retainAll(whitelist);
      }
      out.add(new WidgetRow(filtered));
    }
    return out;
  }

  private WidgetRow buildTotal(ValidatedSpec spec, List<Map<String, Object>> rows) {
    if (spec.template() != WidgetTemplate.STAT_CARD) {
      return null;
    }
    if (rows.isEmpty()) {
      return new WidgetRow(Map.of("value", 0));
    }
    // 집계 결과가 없으면 value 는 null 이다(Map.of 는 null 을 못 담는다). 화면은 null 을 '-' 로 그린다.
    Map<String, Object> total = new LinkedHashMap<>();
    total.put("value", rows.get(0).get("value"));
    return new WidgetRow(total);
  }

  private String unit(ValidatedSpec spec) {
    if (spec.template() == WidgetTemplate.PROGRESS_LIST) {
      return "%";
    }
    return spec.measure().unit();
  }

  private String valueColumnType(ValidatedSpec spec) {
    return switch (spec.measure().valueType()) {
      case RATE_PCT, PCT_POINT -> "percent";
      case DAYS, COUNT -> "number";
    };
  }
}
