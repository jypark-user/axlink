package kr.co.axlink.dashboard.dto;

import java.util.List;

public record WidgetOptions(
    String unit,
    String sort,
    WidgetThreshold threshold,
    Boolean stacked,
    Boolean showLegend,
    Boolean compareWithPrevious,
    List<String> columns) {
}
