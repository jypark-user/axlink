package kr.co.axlink.integration.adapter;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.port.ToolConnector;
import kr.co.axlink.integration.port.ToolConnectorTypes.FetchCursor;
import kr.co.axlink.integration.port.ToolConnectorTypes.FetchPage;
import kr.co.axlink.integration.port.ToolConnectorTypes.RawRecord;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolConnectionSpec;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolProbe;
import org.springframework.stereotype.Component;

/**
 * GitHub 저장소에서 이슈와 풀 리퀘스트를 가져온다.
 * 주소는 API 기준(https://api.github.com), 대상은 owner/repo, 인증은 개인 토큰 하나다.
 */
@Component
public class GithubConnector implements ToolConnector {

  private static final int PER_PAGE = 50;

  @Override
  public ToolType tool() {
    return ToolType.GITHUB;
  }

  @Override
  public ToolProbe verify(ToolConnectionSpec spec) {
    JsonNode repo = ToolHttp.get(repoUrl(spec), headers(spec));
    String name = repo.path("full_name").asText(spec.targetResource());
    return new ToolProbe(true, name, List.of("issue", "pull_request"), null);
  }

  @Override
  public FetchPage fetch(ToolConnectionSpec spec, FetchCursor cursor) {
    StringBuilder url = new StringBuilder(repoUrl(spec))
        .append("/issues?state=all&sort=updated&direction=asc&per_page=").append(PER_PAGE)
        .append("&page=").append(Math.max(1, cursor.page()));
    if (cursor.since() != null) {
      url.append("&since=").append(cursor.since());
    }

    JsonNode body = ToolHttp.get(url.toString(), headers(spec));
    List<RawRecord> records = new ArrayList<>();
    if (body.isArray()) {
      for (JsonNode item : body) {
        records.add(new RawRecord(
            item.path("number").asText(),
            item.has("pull_request") ? "pull_request" : "issue",
            item.path("html_url").asText(null),
            item,
            instant(item.path("updated_at").asText(null))));
      }
    }
    boolean hasMore = records.size() == PER_PAGE;
    return new FetchPage(records, hasMore ? String.valueOf(cursor.page() + 1) : null, hasMore);
  }

  private String repoUrl(ToolConnectionSpec spec) {
    return ToolHttp.base(spec.baseUrl()) + "/repos/" + spec.targetResource();
  }

  private Map<String, String> headers(ToolConnectionSpec spec) {
    String token = spec.credential() == null ? null : spec.credential().secret();
    if (token == null || token.isBlank()) {
      throw new ToolAuthException(401, "개인 토큰이 없습니다.");
    }
    return Map.of(
        "Authorization", "Bearer " + token,
        "Accept", "application/vnd.github+json",
        "X-GitHub-Api-Version", "2022-11-28");
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
