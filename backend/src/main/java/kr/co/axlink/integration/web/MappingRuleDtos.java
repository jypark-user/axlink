package kr.co.axlink.integration.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import kr.co.axlink.integration.domain.MappingSourceKind;
import kr.co.axlink.integration.port.StandardChange.TargetEntity;
import kr.co.axlink.integration.port.WorkProductType;

public final class MappingRuleDtos {

  private MappingRuleDtos() {
  }

  public record Response(
      String id,
      String connectionId,
      MappingSourceKind sourceKind,
      String sourceValue,
      TargetEntity targetEntity,
      WorkProductType targetWorkProductType,
      Map<String, String> statusMap,
      boolean enabled) {
  }

  public record UpsertRequest(
      @NotNull MappingSourceKind sourceKind,
      @NotBlank String sourceValue,
      @NotNull TargetEntity targetEntity,
      WorkProductType targetWorkProductType,
      Map<String, String> statusMap,
      boolean enabled) {
  }

  public record ReplaceRequest(
      @Valid List<UpsertRequest> rules,
      @NotBlank String reapply) {
  }
}
