package kr.co.axlink.dashboard.domain;

import java.time.Instant;
import java.util.UUID;

public record Dashboard(
    UUID id,
    UUID projectId,
    UUID ownerUserId,
    String name,
    String layoutJson,
    boolean isDefault,
    DashboardStatus status,
    Instant createdAt,
    Instant updatedAt) {
}
