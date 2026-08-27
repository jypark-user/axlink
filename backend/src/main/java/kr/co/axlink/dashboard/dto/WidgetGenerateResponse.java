package kr.co.axlink.dashboard.dto;

public record WidgetGenerateResponse(
    String status,
    WidgetSpec spec,
    WidgetDataResponse preview,
    WidgetGenerationRejection rejection) {

  public static final String GENERATED = "GENERATED";
  public static final String NOT_EXPRESSIBLE = "NOT_EXPRESSIBLE";
}
