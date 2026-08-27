package kr.co.axlink.semantic.domain;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;

public record AggregateContext(
    String measureKey,
    List<String> dimensions,
    List<Map<String, Object>> rows,
    Set<UUID> appliedProjectIds,
    WidgetDataResponse data) {
}
