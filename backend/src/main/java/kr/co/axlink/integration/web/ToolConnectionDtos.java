package kr.co.axlink.integration.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.List;
import kr.co.axlink.integration.domain.SyncJobStatus;
import kr.co.axlink.integration.domain.ToolConnectionStatus;
import kr.co.axlink.integration.domain.ToolType;

public final class ToolConnectionDtos {

  private ToolConnectionDtos() {
  }

  public record CreateRequest(
      @NotNull ToolType tool,
      @NotBlank String name,
      @NotBlank String baseUrl,
      @NotBlank String targetResource,
      @Valid @NotNull CredentialRequest credential) {
  }

  public record UpdateRequest(
      String name,
      String baseUrl,
      String targetResource,
      @Valid CredentialRequest credential) {
  }

  public record StatusUpdateRequest(@NotNull ToolConnectionStatus status) {
  }

  public record TestRequest(
      @NotNull ToolType tool,
      @NotBlank String baseUrl,
      @NotBlank String targetResource,
      @Valid @NotNull CredentialRequest credential) {
  }

  public record CredentialRequest(String accessToken) {
  }

  public record TestResponse(
      boolean reachable,
      String resourceName,
      List<String> detectedItemTypes,
      Instant checkedAt) {
  }

  public record Response(
      String id,
      String projectId,
      ToolType tool,
      String name,
      String baseUrl,
      String targetResource,
      String credentialMasked,
      ToolConnectionStatus status,
      Instant lastSyncedAt,
      SyncJobStatus lastSyncStatus,
      String lastSyncError,
      int ingestedCount,
      int mappingRuleCount,
      Instant createdAt) {
  }

  public record SyncTriggerRequest(@NotNull String kind) {
  }
}
