package kr.co.axlink.integration.service;

import java.util.List;
import kr.co.axlink.integration.port.StandardChange;
import kr.co.axlink.integration.port.SyncPromoter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class NoOpSyncPromoter implements SyncPromoter {

  private static final Logger log = LoggerFactory.getLogger(NoOpSyncPromoter.class);

  @Override
  public PromotionStats upsertAll(List<StandardChange> changes, String actor) {
    log.warn("NoOpSyncPromoter active: {} changes dropped (no SyncPromoter implementation)",
        changes == null ? 0 : changes.size());
    return new PromotionStats(0, 0);
  }

  @Override
  public void createAutoTraceLinks(List<StandardChange> codeChanges) {
  }

  @Override
  public void reindexAll(List<StandardChange> changes) {
  }
}
