package kr.co.axlink.integration.service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.integration.adapter.ToolAuthException;
import kr.co.axlink.integration.adapter.ToolConnectorRegistry;
import kr.co.axlink.integration.adapter.ToolRateLimitedException;
import kr.co.axlink.integration.adapter.ToolResourceNotFoundException;
import kr.co.axlink.integration.adapter.ToolUnreachableException;
import kr.co.axlink.integration.domain.SyncJob;
import kr.co.axlink.integration.domain.SyncJobKind;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.mapping.MappingRuleEngine;
import kr.co.axlink.integration.mapping.MappingRules;
import kr.co.axlink.integration.port.StandardChange;
import kr.co.axlink.integration.port.SyncPromoter;
import kr.co.axlink.integration.port.ToolConnector;
import kr.co.axlink.integration.port.ToolConnectorTypes.FetchCursor;
import kr.co.axlink.integration.port.ToolConnectorTypes.FetchPage;
import kr.co.axlink.integration.port.ToolConnectorTypes.RawRecord;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolConnectionSpec;
import kr.co.axlink.integration.repository.RawArtifactRepository;
import kr.co.axlink.integration.repository.ToolConnectionRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class SyncRunner {

  private static final Logger log = LoggerFactory.getLogger(SyncRunner.class);
  private static final Instant EPOCH = Instant.EPOCH;
  private static final int MAX_PAGES = 1000;

  private final SyncJobService syncJobService;
  private final ToolConnectionRepository connectionRepository;
  private final ToolConnectionSecretProvider secretProvider;
  private final ToolConnectorRegistry connectorRegistry;
  private final RawArtifactRepository rawArtifactRepository;
  private final MappingRuleEngine mappingEngine;
  private final SyncPromoter syncPromoter;
  private final JsonCodec jsonCodec;

  public SyncRunner(SyncJobService syncJobService, ToolConnectionRepository connectionRepository,
      ToolConnectionSecretProvider secretProvider, ToolConnectorRegistry connectorRegistry,
      RawArtifactRepository rawArtifactRepository, MappingRuleEngine mappingEngine,
      SyncPromoter syncPromoter, JsonCodec jsonCodec) {
    this.syncJobService = syncJobService;
    this.connectionRepository = connectionRepository;
    this.secretProvider = secretProvider;
    this.connectorRegistry = connectorRegistry;
    this.rawArtifactRepository = rawArtifactRepository;
    this.mappingEngine = mappingEngine;
    this.syncPromoter = syncPromoter;
    this.jsonCodec = jsonCodec;
  }

  public void run(UUID syncJobId) {
    if (syncJobService.claim(syncJobId).isEmpty()) {
      return;
    }
    SyncJob job = syncJobService.findOrThrow(syncJobId);
    try {
      execute(job);
    } catch (Exception e) {
      log.warn("sync job {} failed: {}", syncJobId, e.toString());
      String errorCode = mapErrorCode(e);
      String message = e instanceof ApiException ae && ae.getMessage() != null
          ? ae.getMessage() : (e.getMessage() == null ? errorCode : e.getMessage());
      syncJobService.finishFailed(syncJobId, errorCode, message, SyncStats.empty());
    }
  }

  private void execute(SyncJob job) {
    ToolConnection connection = connectionRepository.findById(job.toolConnectionId())
        .orElseThrow(() -> ApiExceptions.notFound("tool_connection", job.toolConnectionId()));
    MappingRules rules = jsonCodec.read(connection.mappingRulesJson(), MappingRules.class);
    ToolConnectionSpec spec = new ToolConnectionSpec(
        connection.tool(), connection.baseUrl(), connection.targetResource(),
        secretProvider.decrypt(connection));
    Instant cursorFrom = job.kind() == SyncJobKind.BACKFILL ? EPOCH
        : shiftBack(connection.lastSyncedAt());
    Instant cursorTo = Instant.now();

    ToolConnector connector = connectorRegistry.require(connection.tool());
    int fetched = 0;
    int upserted = 0;
    int unmapped = 0;
    int skippedUnchanged = 0;
    List<StandardChange> changes = new ArrayList<>();
    List<StandardChange> codeChanges = new ArrayList<>();

    FetchCursor cursor = new FetchCursor(cursorFrom, null, 1);
    for (int page = 0; page < MAX_PAGES; page++) {
      FetchPage result = connector.fetch(spec, cursor);
      List<RawRecord> records = result.records();
      if (records == null || records.isEmpty()) {
        if (!result.hasMore()) {
          break;
        }
        cursor = new FetchCursor(cursorFrom, result.nextPageToken(), cursor.page() + 1);
        continue;
      }
      fetched += records.size();
      for (RawRecord record : records) {
        String payloadJson = jsonCodec.write(record.payload());
        String contentHash = kr.co.axlink.common.support.Hashes.sha256Hex(payloadJson);
        int affected = rawArtifactRepository.upsert(connection.id(), record.externalId(),
            record.objectKind(), payloadJson, contentHash, Instant.now(), job.id());
        if (affected == 0) {
          skippedUnchanged++;
          continue;
        }
        upserted++;
        java.util.Optional<StandardChange> mapped = mappingEngine.map(
            rules, record, connection.projectId(), connection.id());
        if (mapped.isEmpty()) {
          unmapped++;
          continue;
        }
        StandardChange change = mapped.get();
        changes.add(change);
        if (change.targetEntity() == StandardChange.TargetEntity.CODE_CHANGE) {
          codeChanges.add(change);
        }
      }
      if (!result.hasMore()) {
        break;
      }
      cursor = new FetchCursor(cursorFrom, result.nextPageToken(), cursor.page() + 1);
    }

    if (!changes.isEmpty()) {
      syncPromoter.upsertAll(changes, "system:sync:" + connection.id());
      if (!codeChanges.isEmpty()) {
        syncPromoter.createAutoTraceLinks(codeChanges);
      }
      syncPromoter.reindexAll(changes);
      int indexed = changes.size();
      SyncStats stats = new SyncStats(fetched, upserted, unmapped, indexed, skippedUnchanged);
      syncJobService.finishSucceeded(job.id(), stats, cursorTo);
    } else {
      SyncStats stats = new SyncStats(fetched, upserted, unmapped, 0, skippedUnchanged);
      syncJobService.finishSucceeded(job.id(), stats, cursorTo);
    }
  }

  private Instant shiftBack(Instant lastSyncedAt) {
    if (lastSyncedAt == null) {
      return EPOCH;
    }
    return lastSyncedAt.minusSeconds(60);
  }

  private String mapErrorCode(Exception e) {
    if (e instanceof ToolAuthException) {
      return "TOOL_AUTH_FAILED";
    }
    if (e instanceof ToolResourceNotFoundException) {
      return "TOOL_RESOURCE_NOT_FOUND";
    }
    if (e instanceof ToolRateLimitedException) {
      return "TOOL_RATE_LIMITED";
    }
    if (e instanceof ToolUnreachableException) {
      return "TOOL_UNAVAILABLE";
    }
    if (e instanceof ApiException ae) {
      String name = ae.code().name();
      if (kr.co.axlink.integration.domain.SyncErrorCode.isAllowed(name)) {
        return name;
      }
    }
    return "INTERNAL_ERROR";
  }
}
