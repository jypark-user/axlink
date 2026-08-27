package kr.co.axlink.dashboard.dto;

import kr.co.axlink.dashboard.domain.WidgetTemplate;

public record WidgetSpec(
    WidgetTemplate template,
    String title,
    WidgetQuery query,
    WidgetOptions options) {
}
