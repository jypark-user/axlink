package kr.co.axlink.integration.mapping;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.integration.domain.MappingSourceKind;
import kr.co.axlink.integration.port.StandardChange;
import kr.co.axlink.integration.port.StandardChange.TargetEntity;
import kr.co.axlink.integration.port.ToolConnectorTypes.RawRecord;
import org.springframework.stereotype.Component;

@Component
public class MappingRuleEngine {

  public MappingRuleEngine() {
  }

  public Optional<StandardChange> map(MappingRules rules, RawRecord record,
      UUID projectId, UUID connectionId) {
    if (rules == null || rules.rules() == null) {
      return Optional.empty();
    }
    MappingRules.MappingRule matched = null;
    for (MappingRules.MappingRule rule : rules.rules()) {
      if (!rule.enabled()) {
        continue;
      }
      String key = sourceKey(rule.sourceKind(), record);
      if (key != null && key.equals(rule.sourceValue())) {
        matched = rule;
        break;
      }
    }
    if (matched == null) {
      return Optional.empty();
    }
    Map<String, String> fields = extract(record, matched);
    return Optional.of(new StandardChange(
        projectId,
        connectionId,
        record.externalId(),
        record.externalUrl(),
        matched.targetEntity(),
        matched.targetWorkProductType(),
        fields,
        record.sourceUpdatedAt(),
        record.sourceUpdatedAt(),
        record.payload()));
  }

  private String sourceKey(MappingSourceKind kind, RawRecord record) {
    JsonNode payload = record.payload();
    if (payload == null) {
      return kind == MappingSourceKind.OBJECT_KIND ? record.objectKind() : null;
    }
    return switch (kind) {
      case OBJECT_KIND -> record.objectKind();
      case TRACKER -> text(payload, "tracker", "name");
    };
  }

  /**
   * 도구 응답에서 표준 항목이 쓸 값을 뽑는다.
   * GitHub 은 title/state, Redmine 은 subject/status.name 처럼 이름만 다르고 뜻은 같아
   * 둘 중 있는 쪽을 집는다.
   */
  private Map<String, String> extract(RawRecord record, MappingRules.MappingRule rule) {
    Map<String, String> f = new LinkedHashMap<>();
    JsonNode p = record.payload();
    if (p == null) {
      f.put("status", mapStatus(rule.statusMap(), null, rule.targetEntity()));
      return f;
    }

    put(f, "title", first(text(p, "title"), text(p, "subject")));
    put(f, "body", first(text(p, "body"), text(p, "description")));
    put(f, "assignee", first(
        text(p, "assignee", "login"), text(p, "assigned_to", "name"), text(p, "assignee", "name")));
    put(f, "issueKey", issueKey(p, record));
    put(f, "resolvedAt", first(text(p, "closed_at"), text(p, "closed_on")));
    put(f, "owner", first(text(p, "assigned_to", "name"), text(p, "assignee", "login")));

    // 시정조치는 Redmine 트래커에서만 온다(MappingRuleDefaults.redmineRule).
    // upsertFromTool 이 찾는 키 이름이 이슈와 달라, 같은 값을 그 이름으로도 넣어 준다.
    // 이 줄이 없으면 코드·제목·내용·기한이 전부 비어 INSERT 가 not null 제약에 걸린다.
    if (rule.targetEntity() == TargetEntity.CORRECTION_ACTION) {
      put(f, "code", f.get("issueKey"));
      put(f, "finding", f.get("title"));
      put(f, "action", f.get("body"));
      put(f, "dueDate", text(p, "due_date"));
    }

    String rawStatus = first(text(p, "state"), text(p, "status", "name"));
    f.put("status", mapStatus(rule.statusMap(), rawStatus, rule.targetEntity()));

    String severity = severityOf(p);
    if (severity != null) {
      f.put("severity", severity);
    }
    return f;
  }

  /** 도구가 붙인 번호. 화면과 커밋 메시지가 같은 표기를 쓰도록 # 을 붙여 둔다. */
  private String issueKey(JsonNode p, RawRecord record) {
    String number = first(text(p, "number"), text(p, "id"), record.externalId());
    return number == null ? null : (number.startsWith("#") ? number : "#" + number);
  }

  /** Redmine 우선순위나 GitHub 라벨에서 심각도를 읽는다. 알 수 없으면 비워 두고 기본값에 맡긴다. */
  private String severityOf(JsonNode p) {
    String priority = text(p, "priority", "name");
    if (priority == null) {
      for (JsonNode labelNode : p.path("labels")) {
        String name = labelNode.isTextual() ? labelNode.asText() : labelNode.path("name").asText(null);
        String mapped = severityWord(name);
        if (mapped != null) {
          return mapped;
        }
      }
      return null;
    }
    return severityWord(priority);
  }

  private String severityWord(String raw) {
    if (raw == null) {
      return null;
    }
    String v = raw.toLowerCase();
    if (v.contains("immediate") || v.contains("blocker") || v.contains("즉시")) return "BLOCKER";
    if (v.contains("urgent") || v.contains("critical") || v.contains("긴급")) return "CRITICAL";
    if (v.contains("high") || v.contains("major") || v.contains("높음")) return "MAJOR";
    if (v.contains("low") || v.contains("minor") || v.contains("낮음")) return "MINOR";
    if (v.contains("trivial") || v.contains("사소")) return "TRIVIAL";
    if (v.contains("normal") || v.contains("medium") || v.contains("보통")) return "MAJOR";
    return null;
  }

  private static void put(Map<String, String> f, String key, String value) {
    if (value != null && !value.isBlank()) {
      f.put(key, value);
    }
  }

  private static String first(String... values) {
    for (String v : values) {
      if (v != null && !v.isBlank()) {
        return v;
      }
    }
    return null;
  }

  private String mapStatus(Map<String, String> statusMap, String raw, TargetEntity target) {
    if (raw == null) {
      return defaultStatus(target);
    }
    if (statusMap != null && statusMap.containsKey(raw)) {
      return statusMap.get(raw);
    }
    String normalized = raw.toLowerCase().replace("_", " ").trim();
    if (statusMap != null) {
      for (Map.Entry<String, String> e : statusMap.entrySet()) {
        if (e.getKey() != null && e.getKey().toLowerCase().equals(normalized)) {
          return e.getValue();
        }
      }
    }
    return guessStatus(raw, target);
  }

  private String guessStatus(String raw, TargetEntity target) {
    String lower = raw.toLowerCase();
    return switch (target) {
      case ISSUE -> {
        if (lower.contains("close")) yield "CLOSED";
        if (lower.contains("resolve") || lower.contains("done")) yield "RESOLVED";
        if (lower.contains("progress")) yield "IN_PROGRESS";
        yield "OPEN";
      }
      case REQUIREMENT -> {
        if (lower.contains("accept")) yield "ACCEPTED";
        if (lower.contains("verif")) yield "VERIFIED";
        if (lower.contains("implement")) yield "IMPLEMENTED";
        if (lower.contains("design")) yield "DESIGNED";
        yield "DEFINED";
      }
      case RISK -> {
        if (lower.contains("close")) yield "CLOSED";
        if (lower.contains("mitig")) yield "MITIGATING";
        yield "OPEN";
      }
      case CODE_CHANGE -> lower.contains("merged") ? "MERGED"
          : lower.contains("closed") ? "CLOSED"
              : lower.contains("success") ? "SUCCESS"
                  : lower.contains("failed") ? "FAILED"
                      : lower.contains("canceled") ? "CANCELED" : "OPENED";
      default -> defaultStatus(target);
    };
  }

  private String defaultStatus(TargetEntity target) {
    return switch (target) {
      case ISSUE -> "OPEN";
      case REQUIREMENT -> "DEFINED";
      case RISK -> "OPEN";
      case WORK_PRODUCT -> "NONE";
      case CODE_CHANGE -> "OPENED";
      default -> null;
    };
  }

  private String text(JsonNode node, String... path) {
    JsonNode cur = node;
    for (String key : path) {
      if (cur == null) {
        return null;
      }
      cur = cur.path(key);
    }
    if (cur == null || cur.isMissingNode() || cur.isNull()) {
      return null;
    }
    String s = cur.isTextual() ? cur.asText() : cur.toString();
    return s == null || s.isBlank() ? null : s;
  }
}
