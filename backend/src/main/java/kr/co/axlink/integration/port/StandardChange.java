package kr.co.axlink.integration.port;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public record StandardChange(
    UUID projectId,
    UUID connectionId,
    String externalId,
    String externalUrl,
    TargetEntity targetEntity,
    WorkProductType workProductType,
    Map<String, String> fields,
    Instant sourceCreatedAt,
    Instant sourceUpdatedAt,
    JsonNode payload) {

  public enum TargetEntity {
    REQUIREMENT,
    ISSUE,
    RISK,
    WORK_PRODUCT,
    CORRECTION_ACTION,
    CODE_CHANGE,
    PROGRESS_RECORD,
    TRACE_LINK
  }

  public String field(String key) {
    return fields == null ? null : fields.get(key);
  }
}
