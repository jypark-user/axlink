package kr.co.axlink.project.web;

public record ClosureCheck(
    String key,
    boolean satisfied,
    String detail) {

  public static final String ACCEPTANCE_RECORD_EXISTS = "ACCEPTANCE_RECORD_EXISTS";
  public static final String REQUIRED_WORK_PRODUCTS_APPROVED = "REQUIRED_WORK_PRODUCTS_APPROVED";
  public static final String NO_OPEN_CORRECTION_ACTION = "NO_OPEN_CORRECTION_ACTION";
}
