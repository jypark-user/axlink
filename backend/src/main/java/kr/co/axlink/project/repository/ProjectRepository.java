package kr.co.axlink.project.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.project.domain.Project;
import kr.co.axlink.project.domain.ProjectStatus;
import kr.co.axlink.project.domain.SiPhase;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class ProjectRepository {

  private static final String COLUMNS =
      "id, client_org_id, name, start_date, end_date, description, contractor_name, status, current_si_phase, closed_at, created_at, updated_at";

  private static final Map<String, String> SORT_WHITELIST = Map.of(
      "name", "name",
      "startDate", "start_date",
      "endDate", "end_date",
      "createdAt", "created_at");

  private final JdbcClient jdbcClient;

  public ProjectRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(Project p, String deletePasswordHash) {
    return jdbcClient.sql("""
        insert into project (client_org_id, name, start_date, end_date, description, contractor_name, status, current_si_phase, delete_password_hash)
        values (:clientOrgId, :name, :startDate, :endDate, :description, :contractorName, :status, :currentSiPhase, :deletePasswordHash)
        returning id
        """)
        .param("deletePasswordHash", deletePasswordHash)
        .param("clientOrgId", p.clientOrgId())
        .param("name", p.name())
        .param("startDate", p.startDate())
        .param("endDate", p.endDate())
        .param("description", p.description())
        .param("contractorName", p.contractorName())
        .param("status", p.status() == null ? ProjectStatus.PLANNING.name() : p.status().name())
        .param("currentSiPhase", p.currentSiPhase() == null ? null : p.currentSiPhase().name())
        .query(UUID.class)
        .single();
  }

  /** 삭제 비밀번호 해시. 값이 없으면(옛 사업) 지울 수 없다. */
  public Optional<String> findDeletePasswordHash(UUID id) {
    return jdbcClient.sql("select delete_password_hash from project where id = :id")
        .param("id", id)
        .query(String.class)
        .optional();
  }

  /** 사업 행을 지운다. 하위 자료는 외래키 cascade 로 함께 사라진다 — 되돌릴 수 없다. */
  public int delete(UUID id) {
    return jdbcClient.sql("delete from project where id = :id").param("id", id).update();
  }

  public Optional<Project> findById(UUID id) {
    return jdbcClient.sql("select " + COLUMNS + " from project where id = :id")
        .param("id", id)
        .query(Project.class)
        .optional();
  }

  public List<Project> search(Collection<UUID> projectIds, ProjectStatus status, String q,
      SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select " + COLUMNS + " from project where 1=1");
    Map<String, Object> params = new HashMap<>();
    if (projectIds != null && !projectIds.isEmpty()) {
      sql.append(" and id in (:projectIds)");
      params.put("projectIds", projectIds);
    } else if (projectIds != null) {
      sql.append(" and false");
    }
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and lower(name) like :q");
      params.put("q", "%" + q.toLowerCase() + "%");
    }
    sql.append(" order by ").append(sort.toOrderByClause());
    sql.append(" limit :limit offset :offset");
    params.put("limit", page.limit());
    params.put("offset", page.offset());
    return jdbcClient.sql(sql.toString()).params(params).query(Project.class).list();
  }

  public long countSearch(Collection<UUID> projectIds, ProjectStatus status, String q) {
    StringBuilder sql = new StringBuilder("select count(*) from project where 1=1");
    Map<String, Object> params = new HashMap<>();
    if (projectIds != null && !projectIds.isEmpty()) {
      sql.append(" and id in (:projectIds)");
      params.put("projectIds", projectIds);
    } else if (projectIds != null) {
      sql.append(" and false");
    }
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and lower(name) like :q");
      params.put("q", "%" + q.toLowerCase() + "%");
    }
    Long count = jdbcClient.sql(sql.toString()).params(params).query(Long.class).single();
    return count == null ? 0 : count;
  }

  public Set<UUID> findAllIds() {
    return new LinkedHashSet<>(jdbcClient.sql("select id from project").query(UUID.class).list());
  }

  public Set<UUID> findIdsByClientOrgId(UUID clientOrgId) {
    return new LinkedHashSet<>(jdbcClient.sql("select id from project where client_org_id = :orgId")
        .param("orgId", clientOrgId)
        .query(UUID.class)
        .list());
  }

  public int update(UUID id, String name, LocalDate startDate, LocalDate endDate,
      String description, String contractorName, SiPhase currentSiPhase) {
    return jdbcClient.sql("""
        update project
           set name = coalesce(:name, name),
               start_date = coalesce(:startDate, start_date),
               end_date = coalesce(:endDate, end_date),
               description = coalesce(:description, description),
               contractor_name = coalesce(:contractorName, contractor_name),
               current_si_phase = coalesce(:currentSiPhase, current_si_phase),
               updated_at = now()
         where id = :id
        """)
        .param("id", id)
        .param("name", name)
        .param("startDate", startDate)
        .param("endDate", endDate)
        .param("description", description)
        .param("contractorName", contractorName)
        .param("currentSiPhase", currentSiPhase == null ? null : currentSiPhase.name())
        .update();
  }

  public int close(UUID id, Instant closedAt) {
    return jdbcClient.sql("""
        update project
           set status = 'CLOSED', closed_at = :closedAt, updated_at = now()
         where id = :id
        """)
        .param("id", id)
        .param("closedAt", utc(closedAt))
        .update();
  }

  public int transitionStatus(UUID id, ProjectStatus from, ProjectStatus to) {
    return jdbcClient.sql("""
        update project set status = :to, updated_at = now()
         where id = :id and status = :from
        """)
        .param("id", id)
        .param("to", to.name())
        .param("from", from.name())
        .update();
  }

  public static SortSpec sortSpec(PageQuery page) {
    return SortSpec.parse(page.sort(), SORT_WHITELIST, "created_at desc");
  }

  static OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(ZoneOffset.UTC);
  }
}
