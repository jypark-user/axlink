package kr.co.axlink.standard.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.TraceEntityType;
import kr.co.axlink.standard.domain.TraceLinkKind;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.repository.TraceLinkRepository;
import kr.co.axlink.standard.web.StandardDtos.TraceCell;
import kr.co.axlink.standard.web.StandardDtos.TraceabilityRowResponse;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TraceabilityService {

  private static final int PAGE_SIZE = 200;

  private final JdbcClient jdbc;
  private final TraceLinkRepository traceLinkRepository;
  private final TraceQueryHelper traceQueryHelper;
  private final ProjectAccessResolver accessResolver;

  public TraceabilityService(JdbcClient jdbc, TraceLinkRepository traceLinkRepository,
      TraceQueryHelper traceQueryHelper, ProjectAccessResolver accessResolver) {
    this.jdbc = jdbc;
    this.traceLinkRepository = traceLinkRepository;
    this.traceQueryHelper = traceQueryHelper;
    this.accessResolver = accessResolver;
  }

  @Transactional(readOnly = true)
  public PageResponse<TraceabilityRowResponse> rows(UUID projectId, PageQuery page, AuthPrincipal principal) {
    accessResolver.requireProject(principal, projectId);
    int limit = page.limit();
    int offset = page.offset();
    List<StandardRows.RequirementRow> reqs = jdbc.sql("""
        select id, project_id, code, title, body, priority, status, work_product_id, document_upload_id,
               assignee, tool_connection_id, external_id, external_url, source_kind,
               source_created_at, source_updated_at, created_at, updated_at
          from requirement
         where project_id = :projectId
         order by coalesce(code, title) asc
         limit :limit offset :offset
        """)
        .param("projectId", projectId).param("limit", limit).param("offset", offset)
        .query((rs, n) -> new StandardRows.RequirementRow(
            rs.getObject("id", UUID.class), rs.getObject("project_id", UUID.class),
            rs.getString("code"), rs.getString("title"), rs.getString("body"),
            rs.getString("priority") == null ? null
                : kr.co.axlink.standard.domain.RequirementPriority.valueOf(rs.getString("priority")),
            kr.co.axlink.standard.domain.RequirementStatus.valueOf(rs.getString("status")),
            rs.getObject("work_product_id", UUID.class), rs.getObject("document_upload_id", UUID.class),
            rs.getString("assignee"), rs.getObject("tool_connection_id", UUID.class),
            rs.getString("external_id"), rs.getString("external_url"), rs.getString("source_kind"),
            readInst(rs, "source_created_at"), readInst(rs, "source_updated_at"),
            readInst(rs, "created_at"), readInst(rs, "updated_at")))
        .list();
    long total = jdbc.sql("select count(*) from requirement where project_id = :projectId")
        .param("projectId", projectId).query(Long.class).single();

    List<StandardRows.TraceLinkRow> allLinks = traceLinkRepository.findByProject(projectId);
    Map<UUID, List<StandardRows.TraceLinkRow>> byFrom = new LinkedHashMap<>();
    for (StandardRows.TraceLinkRow l : allLinks) {
      if (l.fromType() == TraceEntityType.REQUIREMENT) {
        byFrom.computeIfAbsent(l.fromId(), k -> new ArrayList<>()).add(l);
      }
    }
    Map<UUID, String> labels = new LinkedHashMap<>();
    List<TraceabilityRowResponse> rowsOut = reqs.stream().map(r -> {
      List<StandardRows.TraceLinkRow> links = byFrom.getOrDefault(r.id(), List.of());
      Map<TraceLinkKind, List<TraceCell>> cells = new LinkedHashMap<>();
      for (TraceLinkKind k : TraceLinkKind.values()) {
        cells.put(k, new ArrayList<>());
      }
      List<TraceLinkKind> broken = new ArrayList<>();
      for (StandardRows.TraceLinkRow l : links) {
        TraceCell cell = new TraceCell(l.toId(),
            traceQueryHelper.labelOf(projectId, l.toType(), l.toId(), labels), null);
        cells.get(l.linkKind()).add(cell);
        if (l.status() == kr.co.axlink.standard.domain.TraceLinkStatus.BROKEN) {
          broken.add(l.linkKind());
        }
      }
      return new TraceabilityRowResponse(r.id(), r.code(), r.title(), r.status(),
          cells.get(TraceLinkKind.DESIGNS), cells.get(TraceLinkKind.IMPLEMENTS),
          cells.get(TraceLinkKind.TESTS), broken);
    }).toList();
    return PageResponse.of(rowsOut, page, total);
  }

  private static java.time.Instant readInst(java.sql.ResultSet rs, String col) throws java.sql.SQLException {
    var ts = rs.getObject(col, java.time.OffsetDateTime.class);
    return ts == null ? null : ts.toInstant();
  }
}
