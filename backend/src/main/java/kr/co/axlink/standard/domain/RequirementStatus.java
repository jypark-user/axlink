package kr.co.axlink.standard.domain;

public enum RequirementStatus {
  DEFINED, DESIGNED, IMPLEMENTED, VERIFIED, ACCEPTED, REJECTED;

  public boolean canTransitionTo(RequirementStatus next) {
    if (next == this || next == null) {
      return false;
    }
    return switch (this) {
      case DEFINED -> next == DESIGNED || next == REJECTED;
      case DESIGNED -> next == IMPLEMENTED || next == REJECTED || next == DEFINED;
      case IMPLEMENTED -> next == VERIFIED || next == REJECTED;
      case VERIFIED -> next == ACCEPTED || next == REJECTED;
      case ACCEPTED -> next == REJECTED;
      case REJECTED -> next == DEFINED || next == DESIGNED;
    };
  }
}
