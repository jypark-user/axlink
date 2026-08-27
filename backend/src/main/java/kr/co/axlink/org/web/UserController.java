package kr.co.axlink.org.web;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.service.InviteService;
import kr.co.axlink.auth.web.InviteDtos.UserInviteLinkResponse;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.org.domain.Role;
import kr.co.axlink.org.domain.UserStatus;
import kr.co.axlink.org.service.UserService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserController {

  private final UserService userService;
  private final InviteService inviteService;

  public UserController(UserService userService, InviteService inviteService) {
    this.userService = userService;
    this.inviteService = inviteService;
  }

  @GetMapping
  public PageResponse<UserResponse> list(
      @RequestParam(required = false) UUID organizationId,
      @RequestParam(required = false) Role role,
      @RequestParam(required = false) UserStatus status,
      @RequestParam(required = false) String q,
      PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return userService.list(organizationId, role, status, q, page);
  }

  @PostMapping
  @PreAuthorize("hasRole('SUPER_ADMIN')")
  public ResponseEntity<UserResponse> create(@Valid @RequestBody UserCreateRequest req) {
    return ResponseEntity.status(HttpStatus.CREATED).body(userService.create(req));
  }

  @GetMapping("/{userId}")
  public UserResponse get(@PathVariable UUID userId) {
    return userService.get(userId);
  }

  @PatchMapping("/{userId}")
  @PreAuthorize("hasRole('SUPER_ADMIN')")
  public UserResponse update(@PathVariable UUID userId, @Valid @RequestBody UserUpdateRequest req) {
    return userService.update(userId, req);
  }

  /** 발송하지 않는다. 관리자가 복사해 전달할 초대 링크 토큰만 발급한다. */
  @PostMapping("/{userId}/invitation-link")
  @PreAuthorize("hasRole('SUPER_ADMIN')")
  public UserInviteLinkResponse createInvitationLink(@PathVariable UUID userId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return inviteService.createUserInviteLink(userId, principal);
  }
}
