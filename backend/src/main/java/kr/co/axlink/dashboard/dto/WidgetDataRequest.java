package kr.co.axlink.dashboard.dto;

import java.util.List;
import java.util.UUID;

public record WidgetDataRequest(
    List<UUID> projectScopeOverride,
    WidgetFilter periodOverride) {
}
