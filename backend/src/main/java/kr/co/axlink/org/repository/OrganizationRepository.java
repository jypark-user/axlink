package kr.co.axlink.org.repository;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.org.domain.OrgStatus;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Organization;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OrganizationRepository {

  private static final String COLUMNS =
      "id, name, type, business_no, status, created_at, updated_at";

  private static final Map<String, String> SORT_WHITELIST = Map.of(
      "name", "name",
      "createdAt", "created_at");

  private final JdbcClient jdbcClient;

  public OrganizationRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(Organization o) {
    return jdbcClient.sql("""
        insert into organization (name, type, business_no, status)
        values (:name, :type, :businessNo, :status)
        returning id
        """)
        .param("name", o.name())
        .param("type", o.type().name())
        .param("businessNo", o.businessNo())
        .param("status", o.status() == null ? OrgStatus.ACTIVE.name() : o.status().name())
        .query(UUID.class)
        .single();
  }

  public Optional<Organization> findById(UUID id) {
    return jdbcClient.sql("select " + COLUMNS + " from organization where id = :id")
        .param("id", id)
        .query(Organization.class)
        .optional();
  }

  public Optional<Organization> findByNameIgnoreCase(String name) {
    return jdbcClient.sql("select " + COLUMNS + " from organization where lower(name) = lower(:name)")
        .param("name", name)
        .query(Organization.class)
        .optional();
  }

  public List<Organization> search(OrgType type, String q, SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select " + COLUMNS + " from organization where 1=1");
    Map<String, Object> params = new java.util.HashMap<>();
    if (type != null) {
      sql.append(" and type = :type");
      params.put("type", type.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and lower(name) like :q");
      params.put("q", "%" + q.toLowerCase() + "%");
    }
    sql.append(" order by ").append(sort.toOrderByClause());
    sql.append(" limit :limit offset :offset");
    params.put("limit", page.limit());
    params.put("offset", page.offset());
    return jdbcClient.sql(sql.toString()).params(params).query(Organization.class).list();
  }

  public long countSearch(OrgType type, String q) {
    StringBuilder sql = new StringBuilder("select count(*) from organization where 1=1");
    Map<String, Object> params = new java.util.HashMap<>();
    if (type != null) {
      sql.append(" and type = :type");
      params.put("type", type.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and lower(name) like :q");
      params.put("q", "%" + q.toLowerCase() + "%");
    }
    Long count = jdbcClient.sql(sql.toString()).params(params).query(Long.class).single();
    return count == null ? 0 : count;
  }

  public int update(UUID id, String name, String businessNo) {
    return jdbcClient.sql("""
        update organization
           set name = :name, business_no = :business_no, updated_at = now()
         where id = :id
        """)
        .param("id", id)
        .param("name", name)
        .param("business_no", businessNo)
        .update();
  }

  public static SortSpec sortSpec(PageQuery page) {
    return SortSpec.parse(page.sort(), SORT_WHITELIST, "created_at desc");
  }

  static OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(ZoneOffset.UTC);
  }
}
