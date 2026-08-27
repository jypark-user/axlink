package kr.co.axlink.standard.service;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.standard.domain.HistoryEntityType;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.history.EntityHistoryRepository;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.repository.TraceLinkRepository;
import kr.co.axlink.standard.web.StandardDtos.EntityHistoryResponse;
import kr.co.axlink.standard.web.StandardDtos.TraceLinkResponse;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class TraceQueryHelper {

  private final TraceLinkRepository traceLinkRepository;
  private final EntityHistoryRepository historyRepository;
  private final JdbcClient jdbc;

  public TraceQueryHelper(TraceLinkRepository traceLinkRepository, EntityHistoryRepository historyRepository,
      JdbcClient jdbc) {
    this.traceLinkRepository = traceLinkRepository;
    this.historyRepository = historyRepository;
    this.jdbc = jdbc;
  }

  public boolean hasAnyTraceLink(UUID projectId, TraceEntityType type, UUID entityId) {
    return !traceLinkRepository.findByFromOrTo(projectId, type, entityId).isEmpty();
  }

  public Map<UUID, Boolean> traceCompleteFlags(UUID projectId, TraceEntityType type, List<UUID> ids) {
    if (ids.isEmpty()) {
      return Map.of();
    }
    Map<UUID, Boolean> result = new HashMap<>();
    for (UUID id : ids) {
      result.put(id, false);
    }
    for (StandardRows.TraceLinkRow l : traceLinkRepository.findByProject(projectId)) {
      if (l.fromType() == type && ids.contains(l.fromId())) {
        result.put(l.fromId(), true);
      }
    }
    return result;
  }

  public List<TraceLinkResponse> linksFor(UUID projectId, TraceEntityType type, UUID entityId) {
    List<StandardRows.TraceLinkRow> rows = traceLinkRepository.findByFromOrTo(projectId, type, entityId);
    Map<UUID, String> labelCache = new LinkedHashMap<>();
    return rows.stream().map(r -> new TraceLinkResponse(r.id(), r.projectId(),
        r.fromType(), r.fromId(), labelOf(projectId, r.fromType(), r.fromId(), labelCache),
        r.toType(), r.toId(), labelOf(projectId, r.toType(), r.toId(), labelCache),
        r.linkKind(), r.origin(), r.status(), externalUrlOf(r), r.createdAt())).toList();
  }

  public List<EntityHistoryResponse> history(HistoryEntityType type, UUID entityId) {
    return historyRepository.search(type, entityId, List.of(), PageQuery.first()).stream()
        .map(h -> new EntityHistoryResponse(h.id(), h.entityType().name(), h.entityId(),
            h.field(), h.fromValue(), h.toValue(), h.actor(), null, h.changedAt()))
        .toList();
  }

  public String labelOf(UUID projectId, TraceEntityType type, UUID id, Map<UUID, String> cache) {
    if (id == null) {
      return null;
    }
    String cached = cache.get(id);
    if (cached != null) {
      return cached;
    }
    String label = resolveLabel(projectId, type, id);
    cache.put(id, label);
    return label;
  }

  private String resolveLabel(UUID projectId, TraceEntityType type, UUID id) {
    String table = switch (type) {
      case REQUIREMENT -> "requirement";
      case ISSUE -> "issue";
      case WORK_PRODUCT -> "work_product";
      case RISK -> "risk";
      case CODE_CHANGE -> "code_change";
      case CHANGE_REQUEST -> "change_request";
      case CORRECTION_ACTION -> "correction_action";
    };
    String titleCol = switch (type) {
      case REQUIREMENT, ISSUE, RISK, CODE_CHANGE, CHANGE_REQUEST -> "title";
      case WORK_PRODUCT -> "coalesce(title, type)";
      case CORRECTION_ACTION -> "finding";
    };
    return jdbc.sql("select " + titleCol + " from " + table + " where id = :id and project_id = :pid")
        .param("id", id).param("pid", projectId).query(String.class).optional()
        .orElse("(삭제됨)");
  }

  private String externalUrlOf(StandardRows.TraceLinkRow r) {
    String url = externalUrl(r.fromType(), r.fromId());
    if (url != null) {
      return url;
    }
    return externalUrl(r.toType(), r.toId());
  }

  private String externalUrl(TraceEntityType type, UUID id) {
    String table = switch (type) {
      case REQUIREMENT -> "requirement";
      case ISSUE -> "issue";
      case WORK_PRODUCT -> "work_product";
      case RISK -> "risk";
      case CODE_CHANGE -> "code_change";
      case CHANGE_REQUEST -> "change_request";
      case CORRECTION_ACTION -> null;
    };
    if (table == null) {
      return null;
    }
    return jdbc.sql("select external_url from " + table + " where id = :id")
        .param("id", id).query(String.class).optional().orElse(null);
  }
}
