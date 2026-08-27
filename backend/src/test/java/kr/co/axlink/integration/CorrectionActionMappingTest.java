package kr.co.axlink.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.integration.domain.MappingSourceKind;
import kr.co.axlink.integration.mapping.MappingRuleEngine;
import kr.co.axlink.integration.mapping.MappingRules;
import kr.co.axlink.integration.port.StandardChange;
import kr.co.axlink.integration.port.StandardChange.TargetEntity;
import kr.co.axlink.integration.port.ToolConnectorTypes.RawRecord;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * CorrectionActionRepository.upsertFromTool 이 찾는 키(code/finding/action/dueDate)와
 * 매핑엔진이 뽑는 키(issueKey/title/body)가 어긋나면 조용히 빈 행이 되고
 * finding 의 not null 제약에 걸린다. 두 이름이 이어져 있는지 굳혀 둔다.
 */
class CorrectionActionMappingTest {

  private static final ObjectMapper JSON = new ObjectMapper();
  private final MappingRuleEngine engine = new MappingRuleEngine();

  private static MappingRules rulesFor(String tracker, TargetEntity target) {
    return new MappingRules(1, List.of(new MappingRules.MappingRule(
        MappingSourceKind.TRACKER, tracker, target, null,
        Map.of("New", "OPEN", "Closed", "DONE"), true)));
  }

  private StandardChange mapRedmineIssue(String tracker, TargetEntity target, String payload) {
    try {
      RawRecord record = new RawRecord("42", "issue", "http://redmine/issues/42",
          JSON.readTree(payload), Instant.EPOCH);
      return engine.map(rulesFor(tracker, target), record, UUID.randomUUID(), UUID.randomUUID())
          .orElseThrow();
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  private static final String REDMINE_CORRECTION = """
      {
        "id": 42,
        "subject": "설계서 버전 표기 누락",
        "description": "표지에 v1.2 를 명시하고 재제출한다",
        "due_date": "2026-09-30",
        "assigned_to": {"name": "홍길동"},
        "status": {"name": "New"},
        "tracker": {"name": "시정조치"}
      }
      """;

  @Test
  @DisplayName("Redmine 시정조치 이슈가 upsert 가 읽는 키로 전달된다")
  void mapsCorrectionFieldsToRepositoryKeys() {
    Map<String, String> f = mapRedmineIssue("시정조치", TargetEntity.CORRECTION_ACTION,
        REDMINE_CORRECTION).fields();

    assertThat(f.get("code")).isEqualTo("#42");
    assertThat(f.get("finding")).isEqualTo("설계서 버전 표기 누락");
    assertThat(f.get("action")).isEqualTo("표지에 v1.2 를 명시하고 재제출한다");
    assertThat(f.get("dueDate")).isEqualTo("2026-09-30");
    assertThat(f.get("owner")).isEqualTo("홍길동");
    assertThat(f.get("status")).isEqualTo("OPEN");
  }

  @Test
  @DisplayName("기한이 없는 이슈도 매핑된다 — 기한은 선택값이다")
  void dueDateIsOptional() {
    Map<String, String> f = mapRedmineIssue("시정조치", TargetEntity.CORRECTION_ACTION, """
        {"id": 7, "subject": "산출물 누락", "status": {"name": "New"}, "tracker": {"name": "시정조치"}}
        """).fields();

    assertThat(f.get("finding")).isEqualTo("산출물 누락");
    assertThat(f).doesNotContainKey("dueDate");
  }

  @Test
  @DisplayName("시정조치가 아닌 대상에는 시정조치 키를 붙이지 않는다")
  void leavesOtherEntitiesUntouched() {
    Map<String, String> f = mapRedmineIssue("버그", TargetEntity.ISSUE, """
        {
          "id": 42,
          "subject": "설계서 버전 표기 누락",
          "description": "표지에 v1.2 를 명시하고 재제출한다",
          "due_date": "2026-09-30",
          "status": {"name": "New"},
          "tracker": {"name": "버그"}
        }
        """).fields();

    assertThat(f.get("title")).isEqualTo("설계서 버전 표기 누락");
    assertThat(f).doesNotContainKeys("code", "finding", "action", "dueDate");
  }
}
