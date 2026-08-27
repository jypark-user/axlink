package kr.co.axlink.standard.domain;

public enum RiskStatus {
  OPEN, MITIGATING, CLOSED;

  public boolean canTransitionTo(RiskStatus next) {
    if (next == this || next == null) {
      return false;
    }
    return switch (this) {
      case OPEN -> next == MITIGATING || next == CLOSED;
      case MITIGATING -> next == CLOSED || next == OPEN;
      case CLOSED -> next == OPEN;
    };
  }
}
