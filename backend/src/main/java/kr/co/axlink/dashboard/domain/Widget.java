package kr.co.axlink.dashboard.domain;

import java.time.Instant;
import java.util.UUID;

public record Widget(
    UUID id,
    UUID dashboardId,
    WidgetTemplate template,
    String title,
    String specJson,
    WidgetStatus status,
    UUID createdByUserId,
    Instant createdAt,
    Instant updatedAt) {
}
