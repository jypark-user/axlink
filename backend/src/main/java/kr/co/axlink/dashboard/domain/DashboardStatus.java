package kr.co.axlink.dashboard.domain;

public enum DashboardStatus {
  ACTIVE,
  DELETED;

  public static DashboardStatus parse(String value) {
    if (value == null) {
      return ACTIVE;
    }
    return DashboardStatus.valueOf(value.toUpperCase(java.util.Locale.ROOT));
  }
}
