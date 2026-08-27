package kr.co.axlink.integration.mapping;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import kr.co.axlink.integration.domain.MappingSourceKind;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.port.StandardChange.TargetEntity;

public final class MappingRuleDefaults {

  private MappingRuleDefaults() {
  }

  private static final Map<String, String> CORRECTION_STATUS = Map.of(
      "New", "OPEN", "Open", "OPEN", "In Progress", "OPEN", "In Review", "OPEN",
      "Done", "DONE", "Closed", "DONE", "Resolved", "DONE");

  /** 도구에 '시정조치' 라는 개념이 없어 이름으로 알아본다. 틀리면 연동 설정에서 규칙을 고치면 된다. */
  private static boolean looksLikeCorrection(String lower) {
    return lower.contains("시정") || lower.contains("correct") || lower.contains("capa")
        || lower.contains("nonconform") || lower.contains("부적합");
  }

  public static MappingRules seedFor(ToolType tool, List<String> detectedItemTypes) {
    List<MappingRules.MappingRule> rules = new ArrayList<>();
    if (detectedItemTypes == null || detectedItemTypes.isEmpty()) {
      return new MappingRules(1, rules);
    }
    switch (tool) {
      case REDMINE -> detectedItemTypes.forEach(tracker -> rules.add(redmineRule(tracker)));
      case GITHUB -> detectedItemTypes.forEach(kind -> rules.add(githubRule(kind)));
    }
    return new MappingRules(1, rules);
  }

  /** GitHub 은 이슈와 풀 리퀘스트 둘뿐이다 — 이슈는 이슈로, 풀 리퀘스트는 코드 변경으로 잇는다. */
  private static MappingRules.MappingRule githubRule(String objectKind) {
    TargetEntity target = "pull_request".equals(objectKind)
        ? TargetEntity.CODE_CHANGE : TargetEntity.ISSUE;
    Map<String, String> statusMap = target == TargetEntity.ISSUE
        ? Map.of("open", "OPEN", "closed", "CLOSED")
        : Map.of();
    return new MappingRules.MappingRule(
        MappingSourceKind.OBJECT_KIND, objectKind, target, null, statusMap, true);
  }

  private static MappingRules.MappingRule redmineRule(String tracker) {
    String lower = tracker.toLowerCase();
    if (looksLikeCorrection(lower)) {
      return new MappingRules.MappingRule(
          MappingSourceKind.TRACKER, tracker, TargetEntity.CORRECTION_ACTION, null,
          CORRECTION_STATUS, true);
    }
    TargetEntity target = lower.contains("feature") || lower.contains("requirement")
        ? TargetEntity.REQUIREMENT : TargetEntity.ISSUE;
    return new MappingRules.MappingRule(
        MappingSourceKind.TRACKER, tracker, target, null, Map.of(), true);
  }
}
