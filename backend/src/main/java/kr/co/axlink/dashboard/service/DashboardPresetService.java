package kr.co.axlink.dashboard.service;

import com.fasterxml.jackson.core.type.TypeReference;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.dashboard.dto.DashboardDetailResponse;
import kr.co.axlink.dashboard.dto.DashboardPresetResponse;
import kr.co.axlink.dashboard.dto.DashboardPresetSaveRequest;
import kr.co.axlink.dashboard.dto.GridItem;
import kr.co.axlink.dashboard.dto.WidgetCreateRequest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 꾸민 대시보드 구성을 이름 붙여 두는 자리. 조직 안에서만 보이고,
 * 담는 것은 위젯 명세와 자리뿐 — 값은 볼 때마다 그 사업 범위로 다시 계산한다.
 */
@Service
public class DashboardPresetService {

  private static final TypeReference<List<WidgetCreateRequest>> ITEMS = new TypeReference<>() {};

  private final DashboardService dashboardService;
  private final JsonCodec jsonCodec;
  private final JdbcClient jdbcClient;

  public DashboardPresetService(DashboardService dashboardService, JsonCodec jsonCodec,
      JdbcClient jdbcClient) {
    this.dashboardService = dashboardService;
    this.jsonCodec = jsonCodec;
    this.jdbcClient = jdbcClient;
  }

  @Transactional(readOnly = true)
  public List<DashboardPresetResponse> list(AuthPrincipal principal) {
    return jdbcClient.sql("""
        select p.id, p.name, jsonb_array_length(p.widgets_json) as widget_count,
               u.name as created_by_name, p.created_at
          from dashboard_preset p
          join app_user u on u.id = p.created_by_user_id
         where p.organization_id = :orgId
         order by p.name
        """)
        .param("orgId", principal.organizationId())
        .query((rs, rowNum) -> new DashboardPresetResponse(
            rs.getObject("id", UUID.class),
            rs.getString("name"),
            rs.getInt("widget_count"),
            rs.getString("created_by_name"),
            rs.getTimestamp("created_at").toInstant()))
        .list();
  }

  /** 프리셋에 담긴 위젯 명세와 자리. 배치는 부르는 쪽이 사업 범위를 채워 넣는다. */
  @Transactional(readOnly = true)
  public List<WidgetCreateRequest> items(UUID presetId, AuthPrincipal principal) {
    String json = jdbcClient
        .sql("select widgets_json from dashboard_preset where id = :id and organization_id = :orgId")
        .param("id", presetId)
        .param("orgId", principal.organizationId())
        .query(String.class)
        .optional()
        .orElseThrow(() -> ApiExceptions.notFound("dashboard_preset", presetId));
    return jsonCodec.read(json, ITEMS);
  }

  /** 같은 이름이면 덮어쓴다 — 이름 하나가 구성 하나를 가리킨다. */
  @Transactional
  public DashboardPresetResponse save(DashboardPresetSaveRequest req, AuthPrincipal principal) {
    DashboardDetailResponse dashboard = dashboardService.get(req.dashboardId(), principal);
    if (dashboard.widgets().isEmpty()) {
      throw ApiExceptions.validationFailed("위젯이 없는 대시보드는 저장할 수 없습니다.");
    }
    Map<String, GridItem> places = dashboard.layout() == null || dashboard.layout().lg() == null
        ? Map.of()
        : dashboard.layout().lg().stream()
            .collect(Collectors.toMap(GridItem::i, g -> g, (a, b) -> a));

    List<WidgetCreateRequest> items = dashboard.widgets().stream()
        .map(w -> new WidgetCreateRequest(w.spec(), places.get(w.id().toString())))
        .toList();

    UUID id = jdbcClient.sql("""
        insert into dashboard_preset (organization_id, created_by_user_id, name, widgets_json)
        values (:orgId, :userId, :name, :widgets::jsonb)
        on conflict (organization_id, name) do update
           set widgets_json = excluded.widgets_json, updated_at = now()
        returning id
        """)
        .param("orgId", principal.organizationId())
        .param("userId", principal.userId())
        .param("name", req.name().trim())
        .param("widgets", jsonCodec.write(items))
        .query(UUID.class)
        .single();

    return list(principal).stream()
        .filter(p -> p.id().equals(id))
        .findFirst()
        .orElseThrow(() -> ApiExceptions.notFound("dashboard_preset", id));
  }

  @Transactional
  public void delete(UUID presetId, AuthPrincipal principal) {
    int deleted = jdbcClient
        .sql("delete from dashboard_preset where id = :id and organization_id = :orgId")
        .param("id", presetId)
        .param("orgId", principal.organizationId())
        .update();
    if (deleted == 0) {
      throw ApiExceptions.notFound("dashboard_preset", presetId);
    }
  }
}
