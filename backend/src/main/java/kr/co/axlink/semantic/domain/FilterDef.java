package kr.co.axlink.semantic.domain;

import java.util.Set;
import java.util.UUID;

public record FilterDef(
    UUID id,
    String key,
    String field,
    FilterOp op,
    String label,
    String description,
    String columnExpr,
    FilterValueType valueType,
    Set<String> enumValues,
    String requiresJoin,
    CatalogStatus status) {

  public static String keyOf(String field, FilterOp op) {
    return field + "__" + op.name().toLowerCase(java.util.Locale.ROOT);
  }
}
