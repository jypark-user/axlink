package kr.co.axlink.auth.web;

import jakarta.validation.Valid;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.service.AuthService;
import kr.co.axlink.auth.service.InviteService;
import kr.co.axlink.auth.web.AuthDtos.LoginRequest;
import kr.co.axlink.auth.web.AuthDtos.LoginResponse;
import kr.co.axlink.auth.web.AuthDtos.MeResponse;
import kr.co.axlink.auth.web.AuthDtos.RefreshTokenRequest;
import kr.co.axlink.auth.web.InviteDtos.AcceptRequest;
import kr.co.axlink.auth.web.InviteDtos.PreviewResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

  private final AuthService authService;
  private final InviteService inviteService;

  public AuthController(AuthService authService, InviteService inviteService) {
    this.authService = authService;
    this.inviteService = inviteService;
  }

  @PostMapping("/login")
  public LoginResponse login(@Valid @RequestBody LoginRequest req,
      @RequestHeader(value = HttpHeaders.USER_AGENT, required = false) String userAgent) {
    return authService.login(req, userAgent);
  }

  @PostMapping("/refresh")
  public LoginResponse refresh(@Valid @RequestBody RefreshTokenRequest req,
      @RequestHeader(value = HttpHeaders.USER_AGENT, required = false) String userAgent) {
    return authService.refresh(req.refreshToken(), userAgent);
  }

  @PostMapping("/logout")
  public ResponseEntity<Void> logout(@RequestBody(required = false) RefreshTokenRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    authService.logout(req == null ? null : req.refreshToken(), principal);
    return ResponseEntity.noContent().build();
  }

  /** 초대 링크 미리보기 — 로그인 없이 연다. */
  @GetMapping("/invitations/{token}")
  public PreviewResponse previewInvitation(@PathVariable String token) {
    return inviteService.preview(token);
  }

  /** 초대 링크로 용역사가 직접 계정을 만들고 곧바로 로그인된다. */
  @PostMapping("/invitations/accept")
  public LoginResponse acceptInvitation(@Valid @RequestBody AcceptRequest req,
      @RequestHeader(value = HttpHeaders.USER_AGENT, required = false) String userAgent) {
    return inviteService.accept(req, userAgent);
  }

  @GetMapping("/me")
  public MeResponse me(@AuthenticationPrincipal AuthPrincipal principal) {
    return authService.me(principal);
  }
}
