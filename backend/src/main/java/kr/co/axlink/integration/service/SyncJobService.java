package kr.co.axlink.integration.service;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.integration.domain.SyncJob;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.SyncJobStatus;
import kr.co.axlink.integration.domain.ToolConnectionStatus;
import kr.co.axlink.integration.repository.SyncJobRepository;
import kr.co.axlink.integration.repository.ToolConnectionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SyncJobService {

  private final SyncJobRepository syncJobRepository;
  private final ToolConnectionRepository connectionRepository;
  private final JsonCodec jsonCodec;

  public SyncJobService(SyncJobRepository syncJobRepository,
      ToolConnectionRepository connectionRepository, JsonCodec jsonCodec) {
    this.syncJobRepository = syncJobRepository;
    this.connectionRepository = connectionRepository;
    this.jsonCodec = jsonCodec;
  }

  public SyncJob enqueue(UUID connectionId, SyncJobKind kind, UUID retryOfJobId) {
    UUID jobId = syncJobRepository.insertQueued(connectionId, kind, null, null, retryOfJobId);
    return findOrThrow(jobId);
  }

  public Optional<UUID> claim(UUID jobId) {
    return syncJobRepository.markRunning(jobId);
  }

  @Transactional
  public void finishSucceeded(UUID jobId, SyncStats stats, Instant cursorTo) {
    String statsJson = jsonCodec.write(stats);
    syncJobRepository.markSucceeded(jobId, statsJson, cursorTo);
    if (cursorTo != null) {
      SyncJob job = findOrThrow(jobId);
      connectionRepository.updateCursor(job.toolConnectionId(), cursorTo, cursorTo.toString());
    }
  }

  @Transactional
  public void finishFailed(UUID jobId, String errorCode, String message, SyncStats stats) {
    String statsJson = jsonCodec.write(stats);
    syncJobRepository.markFailed(jobId, errorCode, message, statsJson);
    SyncJob job = findOrThrow(jobId);
    if ("TOOL_AUTH_FAILED".equals(errorCode)) {
      connectionRepository.updateStatus(job.toolConnectionId(),
          ToolConnectionStatus.FAILED, message);
    } else {
      connectionRepository.updateStatus(job.toolConnectionId(),
          connectionRepository.findById(job.toolConnectionId())
              .map(c -> c.status()).orElse(ToolConnectionStatus.FAILED), message);
    }
  }

  public SyncJob retry(UUID jobId) {
    SyncJob original = findOrThrow(jobId);
    if (original.status() != SyncJobStatus.FAILED) {
      throw ApiExceptions.invalidTransition(original.status(), SyncJobStatus.QUEUED);
    }
    return enqueue(original.toolConnectionId(), original.kind(), original.id());
  }

  public SyncJob cancel(UUID jobId) {
    SyncJob original = findOrThrow(jobId);
    if (original.status() != SyncJobStatus.QUEUED && original.status() != SyncJobStatus.RUNNING) {
      throw ApiExceptions.invalidTransition(original.status(), SyncJobStatus.CANCELLED);
    }
    syncJobRepository.markCancelled(jobId);
    return findOrThrow(jobId);
  }

  public SyncJob findOrThrow(UUID jobId) {
    return syncJobRepository.findById(jobId)
        .orElseThrow(() -> ApiExceptions.notFound("sync_job", jobId));
  }
}
