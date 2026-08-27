package kr.co.axlink.project.service;

import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class ProjectWriteGuard {

  private final JdbcClient jdbcClient;

  public ProjectWriteGuard(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public void assertWritable(UUID projectId) {
    String status = jdbcClient.sql("select status from project where id = :id")
        .param("id", projectId)
        .query(String.class)
        .optional()
        .orElseThrow(() -> ApiExceptions.notFound("project", projectId));
    if ("CLOSED".equals(status)) {
      throw ApiExceptions.projectClosed(projectId);
    }
  }
}
