package kr.co.axlink.integration.service;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.config.AxLinkProperties;
import kr.co.axlink.integration.domain.SyncJob;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.repository.SyncJobRepository;
import kr.co.axlink.integration.repository.ToolConnectionRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SyncScheduler {

  private static final Logger log = LoggerFactory.getLogger(SyncScheduler.class);

  private final ToolConnectionRepository connectionRepository;
  private final SyncJobRepository syncJobRepository;
  private final SyncJobService syncJobService;
  private final SyncDispatcher syncDispatcher;
  private final JdbcClient jdbcClient;
  private final long pollIntervalMs;

  public SyncScheduler(ToolConnectionRepository connectionRepository,
      SyncJobRepository syncJobRepository, SyncJobService syncJobService,
      SyncDispatcher syncDispatcher, JdbcClient jdbcClient, AxLinkProperties properties) {
    this.connectionRepository = connectionRepository;
    this.syncJobRepository = syncJobRepository;
    this.syncJobService = syncJobService;
    this.syncDispatcher = syncDispatcher;
    this.jdbcClient = jdbcClient;
    this.pollIntervalMs = properties.sync().pollIntervalMs();
  }

  @Scheduled(fixedDelayString = "${axlink.sync.poll-interval-ms:900000}", initialDelay = 60000)
  public void pollAll() {
    try {
      Instant dueBefore = Instant.now().minusMillis(pollIntervalMs);
      List<ToolConnection> pollable = connectionRepository.findPollable(dueBefore);
      for (ToolConnection connection : pollable) {
        try {
          if (hasActiveJob(connection.id())) {
            continue;
          }
          SyncJob job = syncJobService.enqueue(connection.id(), SyncJobKind.POLL, null);
          syncDispatcher.dispatch(job.id());
        } catch (Exception e) {
          log.warn("poll enqueue failed for connection {}: {}", connection.id(), e.toString());
        }
      }
    } catch (Exception e) {
      log.error("sync poll cycle failed", e);
    }
  }

  @Scheduled(cron = "0 20 3 * * *")
  public void purgeOldJobs() {
    try {
      Instant cutoff = Instant.now().minus(90, ChronoUnit.DAYS);
      int deleted = syncJobRepository.deleteSucceededBefore(cutoff);
      if (deleted > 0) {
        log.info("purged {} succeeded sync jobs older than {}", deleted, cutoff);
      }
    } catch (Exception e) {
      log.error("sync job purge failed", e);
    }
  }

  private boolean hasActiveJob(UUID connectionId) {
    return !jdbcClient.sql("""
        select 1 from sync_job where tool_connection_id = :id
          and status in ('QUEUED','RUNNING') limit 1
        """)
        .param("id", connectionId).query(Integer.class).list().isEmpty();
  }
}
