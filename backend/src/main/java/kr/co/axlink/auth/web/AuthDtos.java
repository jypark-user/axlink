package kr.co.axlink.auth.web;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Role;

public final class AuthDtos {

  private AuthDtos() {}

  public record LoginRequest(@Email @NotBlank String email, @NotBlank String password) {}

  public record RefreshTokenRequest(@NotBlank String refreshToken) {}

  public record MeResponse(
      UUID userId, String email, String name, Role role, UUID organizationId,
      String organizationName, OrgType organizationType, List<UUID> allowedProjectIds) {}

  public record LoginResponse(
      String accessToken, String refreshToken, long expiresIn, MeResponse user) {}
}
