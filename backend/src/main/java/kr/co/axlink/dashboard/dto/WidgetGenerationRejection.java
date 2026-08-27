package kr.co.axlink.dashboard.dto;

import java.util.List;

public record WidgetGenerationRejection(
    String reason,
    List<String> unmatchedTerms,
    String suggestedAction,
    String suggestedQuestion) {
}
