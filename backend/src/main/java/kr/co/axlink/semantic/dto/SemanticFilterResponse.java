package kr.co.axlink.semantic.dto;

import java.util.List;

public record SemanticFilterResponse(
    String key,
    String field,
    String op,
    String label,
    String valueType,
    List<String> enumValues,
    String status) {
}
