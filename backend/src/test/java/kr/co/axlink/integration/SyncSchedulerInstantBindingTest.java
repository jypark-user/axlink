package kr.co.axlink.integration;

import static org.assertj.core.api.Assertions.assertThatCode;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import kr.co.axlink.integration.repository.SyncJobRepository;
import kr.co.axlink.integration.repository.ToolConnectionRepository;
import kr.co.axlink.integration.service.SyncScheduler;
import kr.co.axlink.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class SyncSchedulerInstantBindingTest extends AbstractIntegrationTest {

  private final ToolConnectionRepository connectionRepository;
  private final SyncJobRepository syncJobRepository;
  private final SyncScheduler syncScheduler;

  @Autowired
  SyncSchedulerInstantBindingTest(ToolConnectionRepository connectionRepository,
      SyncJobRepository syncJobRepository, SyncScheduler syncScheduler) {
    this.connectionRepository = connectionRepository;
    this.syncJobRepository = syncJobRepository;
    this.syncScheduler = syncScheduler;
  }

  @Test
  void findPollableBindsInstantAsTimestamp() {
    assertThatCode(() -> connectionRepository.findPollable(Instant.now()))
        .doesNotThrowAnyException();
  }

  @Test
  void deleteSucceededBeforeBindsInstantAsTimestamp() {
    assertThatCode(
        () -> syncJobRepository.deleteSucceededBefore(Instant.now().minus(90, ChronoUnit.DAYS)))
        .doesNotThrowAnyException();
  }

  @Test
  void scheduledMethodsSurviveOneCycle() {
    assertThatCode(syncScheduler::pollAll).doesNotThrowAnyException();
    assertThatCode(syncScheduler::purgeOldJobs).doesNotThrowAnyException();
  }
}
