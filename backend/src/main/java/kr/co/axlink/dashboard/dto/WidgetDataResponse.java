package kr.co.axlink.dashboard.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.semantic.dto.WidgetColumn;

public record WidgetDataResponse(
    String measure,
    String measureLabel,
    String unit,
    List<String> dimensions,
    List<WidgetColumn> columns,
    List<WidgetRow> rows,
    WidgetRow total,
    WidgetRow previousTotal,
    /** 이 지표의 목표값. 불릿 차트가 기준선을 긋는다 — 목표가 없으면 null. */
    java.math.BigDecimal target,
    List<UUID> appliedProjectIds,
    boolean truncated,
    Instant generatedAt) {
}
