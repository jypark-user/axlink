package kr.co.axlink.dashboard.service;

import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.dashboard.domain.Dashboard;
import kr.co.axlink.dashboard.dto.DashboardCreateRequest;
import kr.co.axlink.dashboard.dto.DashboardDetailResponse;
import kr.co.axlink.dashboard.dto.DashboardLayout;
import kr.co.axlink.dashboard.dto.DashboardLayoutUpdateRequest;
import kr.co.axlink.dashboard.dto.DashboardSummaryResponse;
import kr.co.axlink.dashboard.dto.DashboardUpdateRequest;
import kr.co.axlink.dashboard.dto.GridItem;
import kr.co.axlink.dashboard.dto.WidgetResponse;
import kr.co.axlink.dashboard.repository.DashboardRepository;
import kr.co.axlink.dashboard.repository.WidgetRepository;
import kr.co.axlink.org.domain.Role;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DashboardService {

  private final DashboardRepository dashboardRepository;
  private final WidgetRepository widgetRepository;
  private final JsonCodec jsonCodec;
  private final ProjectAccessResolver accessResolver;

  public DashboardService(DashboardRepository dashboardRepository, WidgetRepository widgetRepository,
      JsonCodec jsonCodec, ProjectAccessResolver accessResolver) {
    this.dashboardRepository = dashboardRepository;
    this.widgetRepository = widgetRepository;
    this.jsonCodec = jsonCodec;
    this.accessResolver = accessResolver;
  }

  public List<DashboardSummaryResponse> list(UUID projectId, AuthPrincipal principal) {
    if (principal.userId() == null) {
      throw ApiExceptions.roleForbidden();
    }
    if (projectId != null) {
      accessResolver.requireProject(principal, projectId);
    }
    return dashboardRepository
        .list(projectId, principal.userId(), accessResolver.allowedProjectIds(principal)).stream()
        .map(d -> new DashboardSummaryResponse(
            d.id(),
            d.name(),
            d.projectId(),
            dashboardRepository.projectName(d.projectId()),
            d.isDefault(),
            widgetRepository.countByDashboard(d.id()),
            editable(d, principal),
            d.updatedAt()))
        .toList();
  }

  @Transactional
  public DashboardDetailResponse create(DashboardCreateRequest req, AuthPrincipal principal) {
    if (req.projectId() != null) {
      requireProjectAccess(req.projectId(), principal);
    }
    String layoutJson = jsonCodec.write(DashboardLayout.empty());
    UUID id = dashboardRepository.create(req.projectId(), principal.userId(), req.name(), layoutJson);
    return get(id, principal);
  }

  public DashboardDetailResponse get(UUID dashboardId, AuthPrincipal principal) {
    Dashboard d = dashboardRepository.find(dashboardId)
        .orElseThrow(() -> ApiExceptions.notFound("dashboard", dashboardId));
    if (!d.ownerUserId().equals(principal.userId()) && d.projectId() != null) {
      accessResolver.requireProject(principal, d.projectId());
    }
    return toDetail(d, principal);
  }

  @Transactional
  public DashboardDetailResponse update(UUID dashboardId, DashboardUpdateRequest req,
      AuthPrincipal principal) {
    Dashboard d = dashboardRepository.find(dashboardId)
        .orElseThrow(() -> ApiExceptions.notFound("dashboard", dashboardId));
    requireEditable(d, principal);
    dashboardRepository.updateName(dashboardId, req.name());
    return get(dashboardId, principal);
  }

  @Transactional
  public void delete(UUID dashboardId, AuthPrincipal principal) {
    Dashboard d = dashboardRepository.find(dashboardId)
        .orElseThrow(() -> ApiExceptions.notFound("dashboard", dashboardId));
    requireEditable(d, principal);
    if (d.isDefault()) {
      throw ApiExceptions.invalidTransition(
          kr.co.axlink.dashboard.domain.DashboardStatus.ACTIVE,
          kr.co.axlink.dashboard.domain.DashboardStatus.DELETED);
    }
    dashboardRepository.softDelete(dashboardId);
  }

  @Transactional
  public DashboardDetailResponse replaceLayout(UUID dashboardId, DashboardLayoutUpdateRequest req,
      AuthPrincipal principal) {
    Dashboard d = dashboardRepository.find(dashboardId)
        .orElseThrow(() -> ApiExceptions.notFound("dashboard", dashboardId));
    requireEditable(d, principal);
    validateLayoutIntegrity(req.layout(), dashboardId);
    dashboardRepository.updateLayout(dashboardId, jsonCodec.write(req.layout()));
    return get(dashboardId, principal);
  }

  private void validateLayoutIntegrity(DashboardLayout layout, UUID dashboardId) {
    List<UUID> widgetIds = widgetRepository.listByDashboard(dashboardId).stream()
        .map(w -> w.id()).toList();
    for (GridItem item : layout.lg() == null ? List.<GridItem>of() : layout.lg()) {
      if (item.i() == null || item.i().isBlank()) {
        throw ApiExceptions.validationFailed("레이아웃 항목 id 가 비어 있습니다.");
      }
      try {
        UUID widgetId = UUID.fromString(item.i());
        if (!widgetIds.contains(widgetId)) {
          throw ApiExceptions.validationFailed(
              "레이아웃이 존재하지 않는 위젯을 참조합니다: " + item.i());
        }
      } catch (IllegalArgumentException e) {
        throw ApiExceptions.validationFailed("레이아웃 항목 id 가 올바르지 않습니다: " + item.i());
      }
    }
  }

  /**
   * 사업 기본 대시보드(진행 상황)는 그 사업의 발주사 담당자가 함께 쓴다.
   * 개인이 따로 만든 대시보드는 만든 사람만 고친다.
   */
  public boolean editable(Dashboard d, AuthPrincipal principal) {
    if (principal.userId() != null && principal.userId().equals(d.ownerUserId())) {
      return true;
    }
    return d.isDefault() && d.projectId() != null && principal.role() == Role.CLIENT
        && accessResolver.allowedProjectIds(principal).contains(d.projectId());
  }

  public void requireEditable(Dashboard d, AuthPrincipal principal) {
    if (!editable(d, principal)) {
      throw ApiExceptions.roleForbidden();
    }
  }

  private void requireProjectAccess(UUID projectId, AuthPrincipal principal) {
    if (principal.userId() == null) {
      throw ApiExceptions.roleForbidden();
    }
    accessResolver.requireProject(principal, projectId);
  }

  private DashboardDetailResponse toDetail(Dashboard d, AuthPrincipal principal) {
    DashboardLayout layout = jsonCodec.read(d.layoutJson(), DashboardLayout.class);
    List<WidgetResponse> widgets = widgetRepository.listByDashboard(d.id()).stream()
        .map(w -> new WidgetResponse(
            w.id(),
            w.dashboardId(),
            w.template().name(),
            w.title(),
            jsonCodec.read(w.specJson(), kr.co.axlink.dashboard.dto.WidgetSpec.class),
            w.createdAt(),
            w.updatedAt()))
        .toList();
    return new DashboardDetailResponse(
        d.id(),
        d.name(),
        d.projectId(),
        dashboardRepository.projectName(d.projectId()),
        d.isDefault(),
        editable(d, principal),
        layout,
        widgets,
        d.updatedAt());
  }
}
