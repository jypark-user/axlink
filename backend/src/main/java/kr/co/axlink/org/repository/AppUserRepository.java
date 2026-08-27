package kr.co.axlink.org.repository;

import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.SortSpec;
import kr.co.axlink.org.domain.AppUser;
import kr.co.axlink.org.domain.Role;
import kr.co.axlink.org.domain.UserStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class AppUserRepository {

  private static final String COLUMNS =
      "id, organization_id, email, name, password_hash, role, status, last_login_at, created_at, updated_at";

  private static final Map<String, String> SORT_WHITELIST = Map.of(
      "name", "name",
      "email", "email",
      "createdAt", "created_at");

  private final JdbcClient jdbcClient;

  public AppUserRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public UUID insert(AppUser u) {
    return jdbcClient.sql("""
        insert into app_user (organization_id, email, name, password_hash, role, status)
        values (:organizationId, :email, :name, :passwordHash, :role, :status)
        returning id
        """)
        .param("organizationId", u.organizationId())
        .param("email", u.email())
        .param("name", u.name())
        .param("passwordHash", u.passwordHash())
        .param("role", u.role().name())
        .param("status", u.status() == null ? UserStatus.INVITED.name() : u.status().name())
        .query(UUID.class)
        .single();
  }

  public Optional<AppUser> findById(UUID id) {
    return jdbcClient.sql("select " + COLUMNS + " from app_user where id = :id")
        .param("id", id)
        .query(AppUser.class)
        .optional();
  }

  public Optional<AppUser> findByEmailIgnoreCase(String email) {
    return jdbcClient.sql("select " + COLUMNS + " from app_user where lower(email) = lower(:email)")
        .param("email", email)
        .query(AppUser.class)
        .optional();
  }

  public List<AppUser> search(UUID organizationId, Role role, UserStatus status, String q,
      SortSpec sort, PageQuery page) {
    StringBuilder sql = new StringBuilder("select " + COLUMNS + " from app_user where 1=1");
    Map<String, Object> params = new HashMap<>();
    if (organizationId != null) {
      sql.append(" and organization_id = :organizationId");
      params.put("organizationId", organizationId);
    }
    if (role != null) {
      sql.append(" and role = :role");
      params.put("role", role.name());
    }
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and (lower(name) like :q or lower(email) like :q)");
      params.put("q", "%" + q.toLowerCase() + "%");
    }
    sql.append(" order by ").append(sort.toOrderByClause());
    sql.append(" limit :limit offset :offset");
    params.put("limit", page.limit());
    params.put("offset", page.offset());
    return jdbcClient.sql(sql.toString()).params(params).query(AppUser.class).list();
  }

  public long countSearch(UUID organizationId, Role role, UserStatus status, String q) {
    StringBuilder sql = new StringBuilder("select count(*) from app_user where 1=1");
    Map<String, Object> params = new HashMap<>();
    if (organizationId != null) {
      sql.append(" and organization_id = :organizationId");
      params.put("organizationId", organizationId);
    }
    if (role != null) {
      sql.append(" and role = :role");
      params.put("role", role.name());
    }
    if (status != null) {
      sql.append(" and status = :status");
      params.put("status", status.name());
    }
    if (q != null && !q.isBlank()) {
      sql.append(" and (lower(name) like :q or lower(email) like :q)");
      params.put("q", "%" + q.toLowerCase() + "%");
    }
    Long count = jdbcClient.sql(sql.toString()).params(params).query(Long.class).single();
    return count == null ? 0 : count;
  }

  public int updateProfile(UUID id, String name, Role role, UserStatus status) {
    return jdbcClient.sql("""
        update app_user
           set name = coalesce(:name, name),
               role = coalesce(:role, role),
               status = coalesce(:status, status),
               updated_at = now()
         where id = :id
        """)
        .param("id", id)
        .param("name", name)
        .param("role", role == null ? null : role.name())
        .param("status", status == null ? null : status.name())
        .update();
  }

  public int updatePasswordHash(UUID id, String passwordHash) {
    return jdbcClient.sql("update app_user set password_hash = :hash, updated_at = now() where id = :id")
        .param("id", id)
        .param("hash", passwordHash)
        .update();
  }

  public int touchLastLogin(UUID id, Instant at) {
    return jdbcClient.sql("update app_user set last_login_at = :at, updated_at = now() where id = :id")
        .param("id", id)
        .param("at", OrganizationRepository.utc(at))
        .update();
  }

  public static SortSpec sortSpec(PageQuery page) {
    return SortSpec.parse(page.sort(), SORT_WHITELIST, "created_at desc");
  }
}
