package kr.co.axlink.semantic.dto;

import java.util.List;

public record SemanticMeasureResponse(
    String key,
    String label,
    String description,
    String unit,
    List<String> allowedDimensions,
    List<String> allowedFilters,
    List<String> defaultTemplates,
    String status) {
}
