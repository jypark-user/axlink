package kr.co.axlink.dashboard.dto;

import java.util.List;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.WidgetTemplate;

public record WidgetGenerateRequest(
    String prompt,
    WidgetTemplate template,
    List<UUID> projectScope,
    UUID dashboardId) {
}
