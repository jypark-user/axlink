package kr.co.axlink.standard.domain;

public enum CorrectionStatus {
  OPEN, DONE, OVERDUE;

  public boolean canTransitionTo(CorrectionStatus next) {
    if (next == this || next == null) {
      return false;
    }
    return switch (this) {
      case OPEN -> next == DONE || next == OVERDUE;
      case OVERDUE -> next == DONE || next == OPEN;
      case DONE -> next == OPEN;
    };
  }
}
