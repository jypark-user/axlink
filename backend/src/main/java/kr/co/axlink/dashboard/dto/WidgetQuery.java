package kr.co.axlink.dashboard.dto;

import java.util.List;
import java.util.UUID;

public record WidgetQuery(
    String measure,
    List<String> dimensions,
    List<WidgetFilter> filters,
    List<UUID> projectScope,
    Integer limit) {
}
