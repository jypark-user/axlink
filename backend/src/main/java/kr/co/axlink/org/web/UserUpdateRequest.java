package kr.co.axlink.org.web;

import kr.co.axlink.org.domain.Role;
import kr.co.axlink.org.domain.UserStatus;

public record UserUpdateRequest(
    String name,
    Role role,
    UserStatus status) {
}
