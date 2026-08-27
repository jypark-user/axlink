package kr.co.axlink.common.support;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class JdbcSupport {

  private final JdbcClient jdbcClient;

  public JdbcSupport(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public <T> Optional<T> one(String sql, Map<String, ?> params, Class<T> type) {
    return jdbcClient.sql(sql).params(params).query(type).optional();
  }

  public <T> List<T> list(String sql, Map<String, ?> params, Class<T> type) {
    return jdbcClient.sql(sql).params(params).query(type).list();
  }

  public boolean exists(String sql, Map<String, ?> params) {
    return !jdbcClient.sql(sql).params(params).query(Integer.class).list().isEmpty();
  }
}
