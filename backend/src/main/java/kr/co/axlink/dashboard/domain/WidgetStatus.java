package kr.co.axlink.dashboard.domain;

public enum WidgetStatus {
  ACTIVE,
  DELETED;

  public static WidgetStatus parse(String value) {
    if (value == null) {
      return ACTIVE;
    }
    return WidgetStatus.valueOf(value.toUpperCase(java.util.Locale.ROOT));
  }
}
