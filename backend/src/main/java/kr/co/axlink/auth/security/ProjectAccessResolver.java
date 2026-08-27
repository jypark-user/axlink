package kr.co.axlink.auth.security;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiExceptions;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class ProjectAccessResolver {

  private final JdbcClient jdbcClient;
  private Set<UUID> cached;

  public ProjectAccessResolver(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public Set<UUID> allowedProjectIds(AuthPrincipal p) {
    if (cached == null) {
      cached = switch (p.role()) {
        case SUPER_ADMIN -> query("select id from project", Map.of());
        case CLIENT -> query("select id from project where client_org_id = :orgId",
            Map.of("orgId", p.organizationId()));
        case CONTRACTOR -> query("""
            select project_id from project_assignment
             where user_id = :userId and status = 'ACTIVE'
            """, Map.of("userId", p.userId()));
      };
    }
    return cached;
  }

  public Set<UUID> resolveScope(AuthPrincipal p, Collection<UUID> requested) {
    Set<UUID> allowed = allowedProjectIds(p);
    if (requested == null || requested.isEmpty()) {
      return allowed;
    }
    Set<UUID> intersection = new LinkedHashSet<>(requested);
    intersection.retainAll(allowed);
    if (intersection.isEmpty()) {
      throw ApiExceptions.projectAccessDenied();
    }
    return intersection;
  }

  public void requireProject(AuthPrincipal p, UUID projectId) {
    if (projectId == null || !allowedProjectIds(p).contains(projectId)) {
      throw ApiExceptions.projectAccessDenied();
    }
  }

  private Set<UUID> query(String sql, Map<String, ?> params) {
    return Set.copyOf(jdbcClient.sql(sql).params(params).query(UUID.class).list());
  }
}
