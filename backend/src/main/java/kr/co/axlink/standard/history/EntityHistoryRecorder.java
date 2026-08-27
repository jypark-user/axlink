package kr.co.axlink.standard.history;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.standard.domain.HistoryEntityType;
import org.springframework.stereotype.Component;

@Component
public class EntityHistoryRecorder {

  private final EntityHistoryRepository repository;

  public EntityHistoryRecorder(EntityHistoryRepository repository) {
    this.repository = repository;
  }

  public void record(HistoryEntityType type, UUID entityId, UUID projectId, String field,
      String from, String to, String actor) {
    if (field == null) {
      return;
    }
    if (equalsNullSafe(from, to)) {
      return;
    }
    repository.insert(type, entityId, projectId, field, from, to, actor);
  }

  public void recordDiff(HistoryEntityType type, UUID entityId, UUID projectId,
      Map<String, String> before, Map<String, String> after, String actor) {
    Map<String, String> beforeMap = before == null ? Map.of() : before;
    Map<String, String> afterMap = after == null ? Map.of() : after;
    Map<String, String> union = new LinkedHashMap<>(beforeMap);
    union.putAll(afterMap);
    for (String field : union.keySet()) {
      String from = beforeMap.get(field);
      String to = afterMap.get(field);
      if (equalsNullSafe(from, to)) {
        continue;
      }
      repository.insert(type, entityId, projectId, field, from, to, actor);
    }
  }

  private static boolean equalsNullSafe(String a, String b) {
    if (a == null && b == null) {
      return true;
    }
    return a != null && a.equals(b);
  }
}
