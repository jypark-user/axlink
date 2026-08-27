package kr.co.axlink.auth.service;

import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.domain.RefreshToken;
import kr.co.axlink.auth.repository.RefreshTokenRepository;
import kr.co.axlink.auth.security.JwtCodec;
import kr.co.axlink.auth.security.JwtProperties;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.auth.web.AuthDtos.LoginRequest;
import kr.co.axlink.auth.web.AuthDtos.LoginResponse;
import kr.co.axlink.auth.web.AuthDtos.MeResponse;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.support.Hashes;
import kr.co.axlink.org.domain.AppUser;
import kr.co.axlink.org.domain.Organization;
import kr.co.axlink.org.domain.UserStatus;
import kr.co.axlink.org.repository.AppUserRepository;
import kr.co.axlink.org.repository.OrganizationRepository;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

  private static final SecureRandom RANDOM = new SecureRandom();

  private final AppUserRepository appUserRepository;
  private final OrganizationRepository organizationRepository;
  private final RefreshTokenRepository refreshTokenRepository;
  private final ProjectAccessResolver projectAccessResolver;
  private final PasswordEncoder passwordEncoder;
  private final JwtCodec jwtCodec;
  private final JwtProperties jwtProperties;

  public AuthService(AppUserRepository appUserRepository,
      OrganizationRepository organizationRepository,
      RefreshTokenRepository refreshTokenRepository,
      ProjectAccessResolver projectAccessResolver,
      PasswordEncoder passwordEncoder,
      JwtCodec jwtCodec,
      JwtProperties jwtProperties) {
    this.appUserRepository = appUserRepository;
    this.organizationRepository = organizationRepository;
    this.refreshTokenRepository = refreshTokenRepository;
    this.projectAccessResolver = projectAccessResolver;
    this.passwordEncoder = passwordEncoder;
    this.jwtCodec = jwtCodec;
    this.jwtProperties = jwtProperties;
  }

  @Transactional
  public LoginResponse login(LoginRequest req, String userAgent) {
    AppUser user = appUserRepository.findByEmailIgnoreCase(req.email())
        .orElseThrow(ApiExceptions::credentialsInvalid);
    if (user.passwordHash() == null
        || !passwordEncoder.matches(req.password(), user.passwordHash())) {
      throw ApiExceptions.credentialsInvalid();
    }
    if (user.status() != UserStatus.ACTIVE) {
      throw ApiExceptions.credentialsInvalid();
    }
    Instant now = Instant.now();
    appUserRepository.touchLastLogin(user.id(), now);
    return issue(user, now, userAgent);
  }

  @Transactional
  public LoginResponse refresh(String refreshToken, String userAgent) {
    Instant now = Instant.now();
    RefreshToken stored = refreshTokenRepository.findByTokenHash(Hashes.sha256Hex(refreshToken))
        .filter(token -> token.usable(now))
        .orElseThrow(ApiExceptions::tokenInvalid);
    AppUser user = appUserRepository.findById(stored.appUserId())
        .filter(found -> found.status() == UserStatus.ACTIVE)
        .orElseThrow(ApiExceptions::tokenInvalid);
    refreshTokenRepository.revoke(stored.id(), now);
    return issue(user, now, userAgent);
  }

  @Transactional
  public void logout(String refreshToken, AuthPrincipal principal) {
    Instant now = Instant.now();
    if (refreshToken == null || refreshToken.isBlank()) {
      refreshTokenRepository.revokeAllByUser(principal.userId(), now);
      return;
    }
    refreshTokenRepository.findByTokenHash(Hashes.sha256Hex(refreshToken))
        .filter(token -> token.appUserId().equals(principal.userId()))
        .ifPresent(token -> refreshTokenRepository.revoke(token.id(), now));
  }

  @Transactional(readOnly = true)
  public MeResponse me(AuthPrincipal principal) {
    AppUser user = appUserRepository.findById(principal.userId())
        .orElseThrow(ApiExceptions::tokenInvalid);
    return toMe(user, organization(user), principal);
  }

  /** 초대 수락 등으로 갓 만들어진 계정에 바로 세션을 발급한다. */
  @Transactional
  public LoginResponse issueSession(AppUser user, String userAgent) {
    return issue(user, Instant.now(), userAgent);
  }

  private LoginResponse issue(AppUser user, Instant now, String userAgent) {
    Organization org = organization(user);
    Instant accessExpiry = now.plus(jwtProperties.accessTtl());
    String accessToken = jwtCodec.sign(Map.of(
        "sub", user.id().toString(),
        "orgId", user.organizationId().toString(),
        "orgType", org.type().name(),
        "role", user.role().name(),
        "iss", jwtProperties.issuer(),
        "iat", now.getEpochSecond(),
        "exp", accessExpiry.getEpochSecond()));
    byte[] raw = new byte[32];
    RANDOM.nextBytes(raw);
    String refreshToken = Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
    refreshTokenRepository.insert(user.id(), Hashes.sha256Hex(refreshToken),
        now.plus(jwtProperties.refreshTtl()), userAgent);
    AuthPrincipal principal =
        new AuthPrincipal(user.id(), user.organizationId(), org.type(), user.role());
    return new LoginResponse(accessToken, refreshToken, jwtProperties.accessTtl().toSeconds(),
        toMe(user, org, principal));
  }

  private MeResponse toMe(AppUser user, Organization org, AuthPrincipal principal) {
    List<UUID> allowedProjectIds = projectAccessResolver.allowedProjectIds(principal)
        .stream()
        .sorted()
        .toList();
    return new MeResponse(user.id(), user.email(), user.name(), user.role(),
        org.id(), org.name(), org.type(), allowedProjectIds);
  }

  private Organization organization(AppUser user) {
    return organizationRepository.findById(user.organizationId())
        .orElseThrow(() -> ApiExceptions.internal("계정의 조직 정보를 찾을 수 없습니다."));
  }
}
