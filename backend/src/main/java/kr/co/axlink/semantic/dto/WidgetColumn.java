package kr.co.axlink.semantic.dto;

public record WidgetColumn(
    String key,
    String label,
    String type) {

  public static WidgetColumn of(String key, String label, String type) {
    return new WidgetColumn(key, label, type);
  }
}
