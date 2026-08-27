package kr.co.axlink.semantic.domain;

public enum CatalogStatus {
  ACTIVE,
  DEPRECATED;

  public static CatalogStatus parse(String value) {
    if (value == null) {
      return ACTIVE;
    }
    return CatalogStatus.valueOf(value.toUpperCase(java.util.Locale.ROOT));
  }
}
