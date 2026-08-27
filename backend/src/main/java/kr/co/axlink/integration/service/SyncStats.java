package kr.co.axlink.integration.service;

public record SyncStats(
    int fetched,
    int upserted,
    int unmapped,
    int indexed,
    int skippedUnchanged) {

  public static SyncStats empty() {
    return new SyncStats(0, 0, 0, 0, 0);
  }

  public SyncStats incFetched() {
    return new SyncStats(fetched + 1, upserted, unmapped, indexed, skippedUnchanged);
  }

  public SyncStats incUpserted() {
    return new SyncStats(fetched, upserted + 1, unmapped, indexed, skippedUnchanged);
  }

  public SyncStats incUnmapped() {
    return new SyncStats(fetched, upserted, unmapped + 1, indexed, skippedUnchanged);
  }

  public SyncStats incIndexed() {
    return new SyncStats(fetched, upserted, unmapped, indexed + 1, skippedUnchanged);
  }

  public SyncStats incSkipped() {
    return new SyncStats(fetched, upserted, unmapped, indexed, skippedUnchanged + 1);
  }
}
