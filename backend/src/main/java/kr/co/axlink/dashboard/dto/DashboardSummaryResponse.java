package kr.co.axlink.dashboard.dto;

import java.time.Instant;
import java.util.UUID;

public record DashboardSummaryResponse(
    UUID id,
    String name,
    UUID projectId,
    String projectName,
    boolean isDefault,
    int widgetCount,
    boolean editable,
    Instant updatedAt) {
}
