package kr.co.axlink.project.service;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.project.web.ProjectMetrics;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class ProjectMetricsReader {

  private static final int REQUIRED_WORK_PRODUCT_TOTAL = 22;

  private final JdbcClient jdbcClient;

  public ProjectMetricsReader(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public Map<UUID, Card> metricsOf(Collection<UUID> projectIds) {
    Map<UUID, Card> cards = new LinkedHashMap<>();
    if (projectIds == null || projectIds.isEmpty()) {
      return cards;
    }
    Map<UUID, long[]> counts = countRequirements(projectIds);
    Map<UUID, long[]> issues = countIssues(projectIds);
    Map<UUID, Long> risks = countOpenRisks(projectIds);
    Map<UUID, long[]> wp = countWorkProducts(projectIds);
    Map<UUID, Long> corrections = countOpenCorrections(projectIds);
    Map<UUID, Integer> trace = traceabilityCoverage(projectIds);
    Map<UUID, Instant> lastSync = lastSyncedAt(projectIds);
    for (UUID id : projectIds) {
      long[] req = counts.getOrDefault(id, new long[]{0, 0});
      long[] iss = issues.getOrDefault(id, new long[]{0, 0});
      long[] wps = wp.getOrDefault(id, new long[]{0, 0});
      Card card = new Card(
          req[0], req[1],
          iss[0], iss[1],
          wps[0], REQUIRED_WORK_PRODUCT_TOTAL,
          trace.getOrDefault(id, 0),
          corrections.getOrDefault(id, 0L),
          lastSync.get(id));
      cards.put(id, card);
    }
    return cards;
  }

  public ProjectMetrics toDetailMetrics(Card card) {
    return new ProjectMetrics(
        card.requirementTotal, card.requirementAccepted,
        card.issueOpen, card.riskOpen,
        card.workProductApproved, card.workProductTotal,
        card.traceabilityCoverage, card.lastSyncedAt);
  }

  private Map<UUID, long[]> countRequirements(Collection<UUID> ids) {
    Map<UUID, long[]> result = new HashMap<>();
    jdbcClient.sql("""
        select project_id,
               count(*) as total,
               count(*) filter (where status in ('VERIFIED','ACCEPTED')) as accepted
          from requirement
         where project_id in (:ids)
         group by project_id
        """)
        .param("ids", ids)
        .query((rs, n) -> {
          result.put(rs.getObject("project_id", UUID.class),
              new long[]{rs.getLong("total"), rs.getLong("accepted")});
          return null;
        }).list();
    return result;
  }

  private Map<UUID, long[]> countIssues(Collection<UUID> ids) {
    Map<UUID, long[]> result = new HashMap<>();
    jdbcClient.sql("""
        select project_id,
               count(*) filter (where status in ('OPEN','IN_PROGRESS')) as open_count,
               count(*) as total
          from issue
         where project_id in (:ids)
         group by project_id
        """)
        .param("ids", ids)
        .query((rs, n) -> {
          result.put(rs.getObject("project_id", UUID.class),
              new long[]{rs.getLong("open_count"), rs.getLong("total")});
          return null;
        }).list();
    return result;
  }

  private Map<UUID, Long> countOpenRisks(Collection<UUID> ids) {
    Map<UUID, Long> result = new HashMap<>();
    jdbcClient.sql("""
        select project_id, count(*) as cnt
          from risk
         where project_id in (:ids) and status <> 'CLOSED'
         group by project_id
        """)
        .param("ids", ids)
        .query((rs, n) -> {
          result.put(rs.getObject("project_id", UUID.class), rs.getLong("cnt"));
          return null;
        }).list();
    return result;
  }

  private Map<UUID, long[]> countWorkProducts(Collection<UUID> ids) {
    Map<UUID, long[]> result = new HashMap<>();
    jdbcClient.sql("""
        select project_id,
               count(*) filter (where status = 'APPROVED') as approved,
               count(*) as total
          from work_product
         where project_id in (:ids) and is_current and applicable
         group by project_id
        """)
        .param("ids", ids)
        .query((rs, n) -> {
          result.put(rs.getObject("project_id", UUID.class),
              new long[]{rs.getLong("approved"), rs.getLong("total")});
          return null;
        }).list();
    return result;
  }

  private Map<UUID, Long> countOpenCorrections(Collection<UUID> ids) {
    Map<UUID, Long> result = new HashMap<>();
    jdbcClient.sql("""
        select project_id, count(*) as cnt
          from correction_action
         where project_id in (:ids) and status = 'OPEN'
         group by project_id
        """)
        .param("ids", ids)
        .query((rs, n) -> {
          result.put(rs.getObject("project_id", UUID.class), rs.getLong("cnt"));
          return null;
        }).list();
    return result;
  }

  private Map<UUID, Integer> traceabilityCoverage(Collection<UUID> ids) {
    Map<UUID, Integer> result = new HashMap<>();
    jdbcClient.sql("""
        with req_totals as (
          select project_id, count(distinct id) as total
            from requirement where project_id in (:ids) group by project_id
        ),
        req_traced as (
          select r.project_id, count(distinct r.id) as traced
            from requirement r
            join trace_link tl
              on tl.to_type = 'REQUIREMENT' and tl.to_id = r.id
             and tl.link_kind = 'TESTS' and tl.status = 'ACTIVE'
           where r.project_id in (:ids)
           group by r.project_id
        )
        select t.project_id,
               case when t.total = 0 then 0
                    else round(100.0 * coalesce(x.traced, 0) / t.total)::int end as coverage
          from req_totals t
          left join req_traced x on x.project_id = t.project_id
        """)
        .param("ids", ids)
        .query((rs, n) -> {
          result.put(rs.getObject("project_id", UUID.class), rs.getInt("coverage"));
          return null;
        }).list();
    return result;
  }

  private Map<UUID, Instant> lastSyncedAt(Collection<UUID> ids) {
    Map<UUID, Instant> result = new HashMap<>();
    jdbcClient.sql("""
        select tc.project_id, max(tc.last_synced_at) as last_synced
          from tool_connection tc
         where tc.project_id in (:ids)
         group by tc.project_id
        """)
        .param("ids", ids)
        .query((rs, n) -> {
          OffsetDateTime odt = rs.getObject("last_synced", OffsetDateTime.class);
          result.put(rs.getObject("project_id", UUID.class), odt == null ? null : odt.toInstant());
          return null;
        }).list();
    return result;
  }

  public record Card(
      long requirementTotal,
      long requirementAccepted,
      long issueOpen,
      long riskOpen,
      long workProductApproved,
      int workProductTotal,
      int traceabilityCoverage,
      long openCorrectionActionCount,
      Instant lastSyncedAt) {
  }
}
