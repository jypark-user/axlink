package kr.co.axlink.integration.web;

import java.time.Instant;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.SyncJobStatus;
import kr.co.axlink.integration.domain.ToolType;

public final class SyncJobDtos {

  private SyncJobDtos() {
  }

  public record Response(
      String id,
      String connectionId,
      String connectionName,
      String projectId,
      ToolType tool,
      SyncJobKind kind,
      SyncJobStatus status,
      Instant startedAt,
      Instant finishedAt,
      Stats stats,
      String error,
      boolean retryable) {
  }

  public record Stats(
      int fetched,
      int upserted,
      int unmapped,
      int indexed,
      int skippedUnchanged) {
  }
}
