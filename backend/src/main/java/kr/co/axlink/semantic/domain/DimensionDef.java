package kr.co.axlink.semantic.domain;

import java.util.UUID;

public record DimensionDef(
    UUID id,
    String key,
    String label,
    String description,
    String selectExpr,
    String labelExpr,
    String requiresJoin,
    DimensionValueType valueType,
    CatalogStatus status) {
}
