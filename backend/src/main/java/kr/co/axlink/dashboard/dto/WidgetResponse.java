package kr.co.axlink.dashboard.dto;

import java.time.Instant;
import java.util.UUID;

public record WidgetResponse(
    UUID id,
    UUID dashboardId,
    String template,
    String title,
    WidgetSpec spec,
    Instant createdAt,
    Instant updatedAt) {
}
