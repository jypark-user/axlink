package kr.co.axlink.auth.web;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.UUID;

public final class InviteDtos {

  private InviteDtos() {}

  /** token은 생성 응답에만 담긴다(해시만 저장하므로 이후에는 다시 볼 수 없다). */
  public record InviteResponse(
      UUID id, UUID projectId, Instant expiresAt, Instant revokedAt, Instant createdAt,
      String token) {}

  /** PROJECT: 용역사가 직접 계정을 만든다. USER: 이미 만들어진 계정의 비밀번호만 정한다. */
  public enum InviteKind { PROJECT, USER }

  public record PreviewResponse(
      InviteKind kind, String projectName, String organizationName, String email, String name,
      Instant expiresAt) {}

  /** contractorOrgName·email·name은 PROJECT 초대에만 쓰인다. */
  public record AcceptRequest(
      @NotBlank String token,
      String contractorOrgName,
      @Email String email,
      String name,
      @NotBlank String password) {}

  public record UserInviteLinkResponse(String token, Instant expiresAt) {}
}
