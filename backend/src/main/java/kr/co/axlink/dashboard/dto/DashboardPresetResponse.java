package kr.co.axlink.dashboard.dto;

import java.time.Instant;
import java.util.UUID;

/** 저장해 둔 대시보드 구성. 목록에서는 몇 장짜리인지만 보여 준다. */
public record DashboardPresetResponse(
    UUID id,
    String name,
    int widgetCount,
    String createdByName,
    Instant createdAt) {
}
