package kr.co.axlink.semantic.domain;

import java.util.Set;
import java.util.UUID;

public record MeasureDef(
    UUID id,
    String key,
    String label,
    String description,
    String baseTable,
    String joinClause,
    String rowFilter,
    String valueExpr,
    MeasureValueType valueType,
    String unit,
    Set<String> allowedDimensions,
    Set<String> allowedFilters,
    String defaultDimension,
    /** 목표값 — 비율 지표는 지금 수치만으로는 좋은지 나쁜지 알 수 없다. 없으면 null. */
    java.math.BigDecimal targetValue,
    CatalogStatus status) {
}
