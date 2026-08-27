package kr.co.axlink.standard.domain;

public enum ChangeRequestStatus {
  REQUESTED, REVIEWING, APPROVED, REJECTED, APPLIED;

  public boolean canTransitionTo(ChangeRequestStatus next) {
    if (next == this || next == null) {
      return false;
    }
    return switch (this) {
      case REQUESTED -> next == REVIEWING;
      case REVIEWING -> next == APPROVED || next == REJECTED;
      case APPROVED -> next == APPLIED;
      case REJECTED -> next == REQUESTED;
      case APPLIED -> false;
    };
  }
}
