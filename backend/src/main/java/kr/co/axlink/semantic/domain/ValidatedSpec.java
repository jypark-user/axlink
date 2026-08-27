package kr.co.axlink.semantic.domain;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetOptions;

public record ValidatedSpec(
    WidgetTemplate template,
    String title,
    MeasureDef measure,
    List<DimensionDef> dimensions,
    List<BoundFilter> filters,
    Set<UUID> projectIds,
    WidgetOptions options,
    Integer limit) {
}
