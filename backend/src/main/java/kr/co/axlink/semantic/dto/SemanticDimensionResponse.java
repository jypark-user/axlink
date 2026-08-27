package kr.co.axlink.semantic.dto;

import java.util.List;

public record SemanticDimensionResponse(
    String key,
    String label,
    String description,
    String valueType,
    List<String> enumValues,
    String status) {
}
