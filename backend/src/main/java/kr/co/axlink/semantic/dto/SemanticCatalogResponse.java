package kr.co.axlink.semantic.dto;

import java.util.List;

public record SemanticCatalogResponse(
    List<SemanticMeasureResponse> measures,
    List<SemanticDimensionResponse> dimensions,
    List<SemanticFilterResponse> filters) {
}
