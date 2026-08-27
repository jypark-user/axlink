package kr.co.axlink.integration.service;

import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class SyncDispatcher {

  private final TaskExecutor syncExecutor;
  private final SyncRunner syncRunner;

  public SyncDispatcher(@Qualifier("syncExecutor") TaskExecutor syncExecutor,
      SyncRunner syncRunner) {
    this.syncExecutor = syncExecutor;
    this.syncRunner = syncRunner;
  }

  public void dispatch(UUID jobId) {
    syncExecutor.execute(() -> syncRunner.run(jobId));
  }
}
