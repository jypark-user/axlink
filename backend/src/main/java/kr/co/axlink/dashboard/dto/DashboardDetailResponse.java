package kr.co.axlink.dashboard.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record DashboardDetailResponse(
    UUID id,
    String name,
    UUID projectId,
    String projectName,
    boolean isDefault,
    boolean editable,
    DashboardLayout layout,
    List<WidgetResponse> widgets,
    Instant updatedAt) {
}
