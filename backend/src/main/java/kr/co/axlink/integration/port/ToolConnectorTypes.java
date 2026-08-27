package kr.co.axlink.integration.port;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;
import kr.co.axlink.integration.domain.ToolType;

public final class ToolConnectorTypes {

  private ToolConnectorTypes() {
  }

  public record ToolConnectionSpec(
      ToolType tool,
      String baseUrl,
      String targetResource,
      ToolCredential credential) {
  }

  public record ToolCredential(String username, String secret) {
  }

  public record ToolProbe(
      boolean reachable,
      String resourceName,
      List<String> detectedItemTypes,
      String errorMessage) {
  }

  public record FetchCursor(Instant since, String pageToken, int page) {
  }

  public record FetchPage(List<RawRecord> records, String nextPageToken, boolean hasMore) {
  }

  public record RawRecord(
      String externalId,
      String objectKind,
      String externalUrl,
      JsonNode payload,
      Instant sourceUpdatedAt) {
  }
}
