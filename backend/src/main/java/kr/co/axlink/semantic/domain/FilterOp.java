package kr.co.axlink.semantic.domain;

public enum FilterOp {
  IN,
  EQ,
  BETWEEN,
  IN_MONTH,
  LAST_N_DAYS,
  GTE,
  LTE;

  public static FilterOp parse(String value) {
    if (value == null) {
      return null;
    }
    return FilterOp.valueOf(value.toUpperCase(java.util.Locale.ROOT));
  }
}
