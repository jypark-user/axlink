package kr.co.axlink.org.service;

import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class CountQueries {

  private final JdbcClient jdbcClient;

  public CountQueries(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public long userCount(UUID organizationId) {
    Long c = jdbcClient.sql("select count(*) from app_user where organization_id = :id")
        .param("id", organizationId)
        .query(Long.class)
        .single();
    return c == null ? 0 : c;
  }

  public long projectCount(UUID organizationId) {
    Long c = jdbcClient.sql("select count(*) from project where client_org_id = :id")
        .param("id", organizationId)
        .query(Long.class)
        .single();
    return c == null ? 0 : c;
  }
}
