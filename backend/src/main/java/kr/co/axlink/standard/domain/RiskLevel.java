package kr.co.axlink.standard.domain;

public enum RiskLevel {
  LOW, MEDIUM, HIGH, CRITICAL;

  public static RiskLevel severityOf(RiskLevel probability, RiskLevel impact) {
    int p = probability == null ? 0 : rankOf(probability);
    int i = impact == null ? 0 : rankOf(impact);
    int score = p + i;
    if (score >= 6) {
      return CRITICAL;
    }
    if (score >= 4) {
      return HIGH;
    }
    if (score >= 2) {
      return MEDIUM;
    }
    return LOW;
  }

  private static int rankOf(RiskLevel v) {
    return switch (v) {
      case LOW -> 1;
      case MEDIUM -> 2;
      case HIGH -> 3;
      case CRITICAL -> 4;
    };
  }
}
