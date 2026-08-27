package kr.co.axlink.semantic.service;

public final class TimeColumns {

  private TimeColumns() {
  }

  public static String of(String baseTable) {
    return switch (baseTable) {
      case "requirement" -> "e.source_created_at";
      case "issue" -> "coalesce(e.source_created_at, e.created_at)";
      case "work_product" -> "coalesce(e.submitted_at, e.created_at)";
      case "risk" -> "e.created_at";
      case "code_change" -> "e.occurred_at";
      case "change_request" -> "e.requested_at";
      case "correction_action" -> "e.created_at";
      case "progress_record" -> "e.period_end";
      default -> throw new IllegalArgumentException(
          "알 수 없는 base_table: " + baseTable);
    };
  }
}
