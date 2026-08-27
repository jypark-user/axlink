package kr.co.axlink.integration.mapping;

import java.util.List;
import java.util.Map;
import kr.co.axlink.integration.domain.MappingSourceKind;
import kr.co.axlink.integration.port.StandardChange.TargetEntity;
import kr.co.axlink.integration.port.WorkProductType;

public record MappingRules(int version, List<MappingRule> rules) {

  public record MappingRule(
      MappingSourceKind sourceKind,
      String sourceValue,
      TargetEntity targetEntity,
      WorkProductType targetWorkProductType,
      Map<String, String> statusMap,
      boolean enabled) {
  }
}
