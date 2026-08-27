package kr.co.axlink.standard.service;

import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.co.axlink.integration.port.StandardChange;
import kr.co.axlink.integration.port.SyncPromoter;
import kr.co.axlink.rag.domain.DocSourceType;
import kr.co.axlink.rag.service.IndexingService;
import kr.co.axlink.standard.domain.CodeChangeKind;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.domain.TraceLinkDraft;
import kr.co.axlink.standard.domain.TraceLinkKind;
import kr.co.axlink.standard.repository.CodeChangeRepository;
import kr.co.axlink.standard.repository.CorrectionActionRepository;
import kr.co.axlink.standard.repository.GovernanceRepository;
import kr.co.axlink.standard.repository.IssueRepository;
import kr.co.axlink.standard.repository.RequirementRepository;
import kr.co.axlink.standard.repository.RiskRepository;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.repository.WorkProductRepository;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StandardEntityService implements SyncPromoter {

  /**
   * 커밋 메시지·본문에서 이슈를 가리키는 말.
   * GitHub·Redmine 은 #123 으로 적고, 도구가 접두어를 붙여 주면 ABC-123 꼴도 온다.
   */
  private static final Pattern ISSUE_KEY =
      Pattern.compile("\\b[A-Z][A-Z0-9_]+-\\d+\\b|#\\d+\\b");

  private final RequirementRepository requirementRepository;
  private final IssueRepository issueRepository;
  private final RiskRepository riskRepository;
  private final WorkProductRepository workProductRepository;
  private final CodeChangeRepository codeChangeRepository;
  private final GovernanceRepository governanceRepository;
  private final CorrectionActionRepository correctionActionRepository;
  private final TraceLinkService traceLinkService;
  private final IndexingService indexingService;
  private final JdbcClient jdbc;

  public StandardEntityService(RequirementRepository requirementRepository, IssueRepository issueRepository,
      RiskRepository riskRepository, WorkProductRepository workProductRepository,
      CodeChangeRepository codeChangeRepository, GovernanceRepository governanceRepository,
      CorrectionActionRepository correctionActionRepository,
      TraceLinkService traceLinkService, IndexingService indexingService, JdbcClient jdbc) {
    this.requirementRepository = requirementRepository;
    this.issueRepository = issueRepository;
    this.riskRepository = riskRepository;
    this.workProductRepository = workProductRepository;
    this.codeChangeRepository = codeChangeRepository;
    this.governanceRepository = governanceRepository;
    this.correctionActionRepository = correctionActionRepository;
    this.traceLinkService = traceLinkService;
    this.indexingService = indexingService;
    this.jdbc = jdbc;
  }

  @Override
  @Transactional
  public PromotionStats upsertAll(List<StandardChange> changes, String actor) {
    int upserted = 0;
    int unchanged = 0;
    for (StandardChange c : changes) {
      StandardRows.UpsertOutcome outcome = dispatch(c);
      if (outcome == null) {
        unchanged++;
      } else {
        upserted++;
      }
    }
    return new PromotionStats(upserted, unchanged);
  }

  @Override
  @Transactional
  public void createAutoTraceLinks(List<StandardChange> codeChanges) {
    for (StandardChange c : codeChanges) {
      if (c.targetEntity() != StandardChange.TargetEntity.CODE_CHANGE) {
        continue;
      }
      String title = c.field("title");
      if (title == null) {
        continue;
      }
      UUID codeChangeId = codeChangeRepository.findBySource(c.connectionId(), c.externalId())
          .map(StandardRows.CodeChangeRow::id).orElse(null);
      if (codeChangeId == null) {
        continue;
      }
      List<TraceLinkDraft> drafts = new ArrayList<>();
      for (UUID issueId : findIssueIdsByKeys(c.projectId(), title)) {
        drafts.add(new TraceLinkDraft(TraceEntityType.CODE_CHANGE, codeChangeId,
            TraceEntityType.ISSUE, issueId, TraceLinkKind.IMPLEMENTS));
      }
      if (!drafts.isEmpty()) {
        traceLinkService.createAuto(c.projectId(), drafts);
      }
    }
  }

  @Override
  @Transactional
  public void reindexAll(List<StandardChange> changes) {
    Map<DocSourceType, Set<UUID>> changed = new LinkedHashMap<>();
    for (StandardChange c : changes) {
      DocSourceType type = mapType(c.targetEntity());
      if (type == null) {
        continue;
      }
      UUID id = findPromotedId(c);
      if (id != null) {
        changed.computeIfAbsent(type, k -> new LinkedHashSet<>()).add(id);
      }
    }
    if (!changed.isEmpty()) {
      indexingService.reindexAll(changed);
    }
  }

  private StandardRows.UpsertOutcome dispatch(StandardChange c) {
    Map<String, Object> f = fields(c);
    return switch (c.targetEntity()) {
      case REQUIREMENT -> requirementRepository.upsertFromTool(c.projectId(), c.connectionId(),
          c.externalId(), c.externalUrl(), f, c.sourceCreatedAt(), c.sourceUpdatedAt()).orElse(null);
      case ISSUE -> issueRepository.upsertFromTool(c.projectId(), c.connectionId(), c.externalId(),
          c.externalUrl(), f, c.sourceCreatedAt(), c.sourceUpdatedAt()).orElse(null);
      case RISK -> riskRepository.upsertFromTool(c.projectId(), c.connectionId(), c.externalId(),
          c.externalUrl(), f).orElse(null);
      case WORK_PRODUCT -> workProductRepository.upsertFromTool(c.projectId(), c.connectionId(),
          c.externalId(), c.externalUrl(), c.workProductType(), f).orElse(null);
      case CODE_CHANGE -> codeChangeRepository.upsertFromTool(c.projectId(), c.connectionId(),
          c.externalId(), c.externalUrl(), CodeChangeKind.valueOf(c.field("kind")), f,
          parseInstant(c.field("occurredAt"))).orElse(null);
      case PROGRESS_RECORD -> governanceRepository.upsertProgressFromTool(c.projectId(),
          c.connectionId(), c.externalId(), c.externalUrl(),
          parseDate(c.field("periodStart")), parseDate(c.field("periodEnd")),
          parseDouble(c.field("plannedPct")), parseDouble(c.field("actualPct")),
          c.field("summary")).orElse(null);
      case CORRECTION_ACTION -> correctionActionRepository.upsertFromTool(c.projectId(),
          c.connectionId(), c.externalId(), c.externalUrl(), correctionFields(c, f)).orElse(null);
      case TRACE_LINK -> null;
    };
  }

  /** 도구의 이슈 모양을 시정조치 모양으로 옮긴다. 지적사항=제목, 조치=본문, 담당=담당자. */
  private Map<String, Object> correctionFields(StandardChange c, Map<String, Object> f) {
    Map<String, Object> m = new LinkedHashMap<>();
    Object code = f.get("issueKey");
    m.put("code", code == null ? c.externalId() : code);
    m.put("finding", f.get("title"));
    m.put("action", f.get("body"));
    m.put("owner", f.get("assignee"));
    m.put("dueDate", parseDate(str(f.get("dueDate"))));
    m.put("status", f.getOrDefault("status", "OPEN"));
    return m;
  }

  private static String str(Object v) {
    return v == null ? null : v.toString();
  }

  private Map<String, Object> fields(StandardChange c) {
    Map<String, Object> m = new LinkedHashMap<>();
    if (c.fields() != null) {
      m.putAll(c.fields());
    }
    Instant resolved = parseInstant(c.field("resolvedAt"));
    if (resolved != null) {
      m.put("resolvedAt", resolved);
    }
    return m;
  }

  private UUID findPromotedId(StandardChange c) {
    return switch (c.targetEntity()) {
      case REQUIREMENT -> requirementRepository.findBySource(c.connectionId(), c.externalId())
          .map(StandardRows.RequirementRow::id).orElse(null);
      case ISSUE -> issueRepository.findBySource(c.connectionId(), c.externalId())
          .map(StandardRows.IssueRow::id).orElse(null);
      case WORK_PRODUCT -> workProductRepository.findByTypeCurrent(c.projectId(), c.workProductType())
          .map(StandardRows.WorkProductRow::id).orElse(null);
      case RISK, CODE_CHANGE, PROGRESS_RECORD, CORRECTION_ACTION, TRACE_LINK -> null;
    };
  }

  private DocSourceType mapType(StandardChange.TargetEntity t) {
    return switch (t) {
      case REQUIREMENT -> DocSourceType.REQUIREMENT;
      case ISSUE -> DocSourceType.ISSUE;
      case WORK_PRODUCT -> DocSourceType.WORK_PRODUCT;
      case RISK -> DocSourceType.RISK;
      case PROGRESS_RECORD -> DocSourceType.PROGRESS_RECORD;
      case CORRECTION_ACTION -> DocSourceType.CORRECTION_ACTION;
      case CODE_CHANGE, TRACE_LINK -> null;
    };
  }

  private List<UUID> findIssueIdsByKeys(UUID projectId, String text) {
    Matcher m = ISSUE_KEY.matcher(text);
    List<UUID> ids = new ArrayList<>();
    Set<String> seen = new LinkedHashSet<>();
    while (m.find()) {
      seen.add(m.group());
    }
    for (String key : seen) {
      // 도구가 '#' 을 붙여 저장하기도, 숫자만 저장하기도 한다 — 둘 다 맞춰 본다.
      List<String> candidates = key.startsWith("#")
          ? List.of(key, key.substring(1))
          : List.of(key);
      jdbc.sql("select id from issue where project_id = :pid and issue_key = any(:keys)")
          .param("pid", projectId).param("keys", candidates.toArray(String[]::new))
          .query(UUID.class).optional().ifPresent(ids::add);
    }
    return ids;
  }

  private static Instant parseInstant(String s) {
    if (s == null || s.isBlank()) {
      return null;
    }
    try {
      return Instant.parse(s);
    } catch (Exception e) {
      return null;
    }
  }

  private static LocalDate parseDate(String s) {
    if (s == null || s.isBlank()) {
      return null;
    }
    try {
      return LocalDate.parse(s);
    } catch (Exception e) {
      return null;
    }
  }

  private static double parseDouble(String s) {
    if (s == null || s.isBlank()) {
      return 0;
    }
    try {
      return Double.parseDouble(s);
    } catch (Exception e) {
      return 0;
    }
  }
}
