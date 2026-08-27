package kr.co.axlink.integration.port;

import java.util.List;

public interface SyncPromoter {

  PromotionStats upsertAll(List<StandardChange> changes, String actor);

  void createAutoTraceLinks(List<StandardChange> codeChanges);

  void reindexAll(List<StandardChange> changes);

  record PromotionStats(int upserted, int unchanged) {
  }
}
