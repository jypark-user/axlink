package kr.co.axlink.integration.web;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.integration.mapping.MappingRules;
import kr.co.axlink.integration.service.ToolConnectionService;
import kr.co.axlink.integration.web.MappingRuleDtos.ReplaceRequest;
import kr.co.axlink.integration.web.MappingRuleDtos.Response;
import kr.co.axlink.integration.web.MappingRuleDtos.UpsertRequest;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class MappingRuleController {

  private final ToolConnectionService connectionService;

  public MappingRuleController(ToolConnectionService connectionService) {
    this.connectionService = connectionService;
  }

  @GetMapping("/connections/{connectionId}/mapping-rules")
  public List<Response> list(@PathVariable UUID connectionId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    MappingRules rules = connectionService.getMappingRules(connectionId, principal);
    return toResponseList(connectionId, rules);
  }

  @PutMapping("/connections/{connectionId}/mapping-rules")
  public List<Response> replace(@PathVariable UUID connectionId, @RequestBody ReplaceRequest request,
      @AuthenticationPrincipal AuthPrincipal principal) {
    List<MappingRules.MappingRule> rules = new ArrayList<>();
    if (request.rules() != null) {
      for (UpsertRequest upsert : request.rules()) {
        rules.add(new MappingRules.MappingRule(
            upsert.sourceKind(), upsert.sourceValue(), upsert.targetEntity(),
            upsert.targetWorkProductType(), upsert.statusMap(), upsert.enabled()));
      }
    }
    MappingRules replaced = new MappingRules(1, rules);
    boolean reapplyNow = "BACKFILL_NOW".equalsIgnoreCase(request.reapply());
    MappingRules saved = connectionService.replaceMappingRules(connectionId, replaced,
        reapplyNow, principal);
    return toResponseList(connectionId, saved);
  }

  private List<Response> toResponseList(UUID connectionId, MappingRules rules) {
    List<Response> out = new ArrayList<>();
    if (rules == null || rules.rules() == null) {
      return out;
    }
    int index = 0;
    for (MappingRules.MappingRule rule : rules.rules()) {
      out.add(new Response(
          connectionId.toString() + "-" + index,
          connectionId.toString(),
          rule.sourceKind(),
          rule.sourceValue(),
          rule.targetEntity(),
          rule.targetWorkProductType(),
          rule.statusMap(),
          rule.enabled()));
      index++;
    }
    return out;
  }
}
