package kr.co.axlink.standard.domain;

public enum AcceptanceStatus {
  ISSUED, VOIDED;

  public boolean canTransitionTo(AcceptanceStatus next) {
    return next != null && this == ISSUED && next == VOIDED;
  }
}
