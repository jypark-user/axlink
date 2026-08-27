package kr.co.axlink.integration.adapter;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.port.ToolConnector;
import kr.co.axlink.integration.port.ToolConnectorTypes.FetchCursor;
import kr.co.axlink.integration.port.ToolConnectorTypes.FetchPage;
import kr.co.axlink.integration.port.ToolConnectorTypes.RawRecord;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolConnectionSpec;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolProbe;
import org.springframework.stereotype.Component;

/**
 * Redmine 프로젝트에서 이슈를 가져온다.
 * 주소는 Redmine 루트, 대상은 프로젝트 식별자, 인증은 API 키 하나다.
 * 이슈 종류(트래커)는 매핑 규칙이 가르는 기준이라 탐지해서 함께 돌려준다.
 */
@Component
public class RedmineConnector implements ToolConnector {

  private static final int LIMIT = 50;
  /** Redmine 은 updated_on 을 'yyyy-MM-ddTHH:mm:ssZ' 로 받는다. */
  private static final DateTimeFormatter STAMP =
      DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'");

  @Override
  public ToolType tool() {
    return ToolType.REDMINE;
  }

  @Override
  public ToolProbe verify(ToolConnectionSpec spec) {
    String base = ToolHttp.base(spec.baseUrl());
    JsonNode project = ToolHttp.get(
        base + "/projects/" + spec.targetResource() + ".json", headers(spec));
    String name = project.path("project").path("name").asText(spec.targetResource());
    return new ToolProbe(true, name, trackers(base, spec), null);
  }

  @Override
  public FetchPage fetch(ToolConnectionSpec spec, FetchCursor cursor) {
    int page = Math.max(1, cursor.page());
    StringBuilder url = new StringBuilder(ToolHttp.base(spec.baseUrl()))
        .append("/issues.json?project_id=").append(spec.targetResource())
        .append("&status_id=*&sort=updated_on&limit=").append(LIMIT)
        .append("&offset=").append((page - 1) * LIMIT);
    if (cursor.since() != null) {
      url.append("&updated_on=%3E%3D").append(
          STAMP.format(LocalDateTime.ofInstant(cursor.since(), ZoneOffset.UTC)));
    }

    JsonNode body = ToolHttp.get(url.toString(), headers(spec));
    List<RawRecord> records = new ArrayList<>();
    for (JsonNode item : body.path("issues")) {
      String id = item.path("id").asText();
      records.add(new RawRecord(
          id,
          "issue",
          ToolHttp.base(spec.baseUrl()) + "/issues/" + id,
          item,
          instant(item.path("updated_on").asText(null))));
    }

    int total = body.path("total_count").asInt(records.size());
    boolean hasMore = (long) page * LIMIT < total;
    return new FetchPage(records, hasMore ? String.valueOf(page + 1) : null, hasMore);
  }

  /** 이 프로젝트에서 실제로 쓰는 트래커 이름. 못 읽으면 빈 목록으로 두고 기본 규칙에 맡긴다. */
  private List<String> trackers(String base, ToolConnectionSpec spec) {
    Set<String> names = new LinkedHashSet<>();
    try {
      JsonNode body = ToolHttp.get(base + "/trackers.json", headers(spec));
      for (JsonNode tracker : body.path("trackers")) {
        String name = tracker.path("name").asText(null);
        if (name != null && !name.isBlank()) {
          names.add(name);
        }
      }
    } catch (RuntimeException e) {
      return List.of();
    }
    return List.copyOf(names);
  }

  private Map<String, String> headers(ToolConnectionSpec spec) {
    String key = spec.credential() == null ? null : spec.credential().secret();
    if (key == null || key.isBlank()) {
      throw new ToolAuthException(401, "API 키가 없습니다.");
    }
    return Map.of("X-Redmine-API-Key", key, "Accept", "application/json");
  }

  private static Instant instant(String raw) {
    if (raw == null || raw.isBlank()) {
      return null;
    }
    try {
      return Instant.parse(raw);
    } catch (Exception e) {
      return null;
    }
  }
}
