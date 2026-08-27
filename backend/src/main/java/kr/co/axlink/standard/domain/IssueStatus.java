package kr.co.axlink.standard.domain;

public enum IssueStatus {
  OPEN, IN_PROGRESS, RESOLVED, CLOSED;

  public boolean canTransitionTo(IssueStatus next) {
    if (next == this || next == null) {
      return false;
    }
    return switch (this) {
      case OPEN -> next == IN_PROGRESS;
      case IN_PROGRESS -> next == RESOLVED || next == OPEN;
      case RESOLVED -> next == CLOSED || next == IN_PROGRESS;
      case CLOSED -> next == IN_PROGRESS;
    };
  }
}
