package kr.co.axlink.standard.service;

import java.util.UUID;
import kr.co.axlink.standard.repository.CorrectionActionRepository;
import kr.co.axlink.standard.repository.WorkProductRepository;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class CorrectionOverdueScheduler {

  private final CorrectionActionRepository correctionActionRepository;
  private final WorkProductRepository workProductRepository;
  private final JdbcClient jdbc;

  public CorrectionOverdueScheduler(CorrectionActionRepository correctionActionRepository,
      WorkProductRepository workProductRepository, JdbcClient jdbc) {
    this.correctionActionRepository = correctionActionRepository;
    this.workProductRepository = workProductRepository;
    this.jdbc = jdbc;
  }

  @Scheduled(cron = "0 7 2 * * *")
  public void sweepOverdue() {
    correctionActionRepository.sweepOverdue();
  }

  @Scheduled(cron = "0 23 2 * * *")
  public void backfillMissingChecklistRows() {
    jdbc.sql("select distinct project_id from project where status <> 'CLOSED'")
        .query(UUID.class).list()
        .forEach(workProductRepository::backfillMissingChecklistRows);
  }
}
