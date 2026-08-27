package kr.co.axlink.dashboard.service;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.dashboard.domain.Dashboard;
import kr.co.axlink.dashboard.domain.Widget;
import kr.co.axlink.dashboard.dto.GridItem;
import kr.co.axlink.dashboard.dto.WidgetCreateRequest;
import kr.co.axlink.dashboard.dto.WidgetDataRequest;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetResponse;
import kr.co.axlink.dashboard.dto.WidgetSpec;
import kr.co.axlink.dashboard.dto.WidgetUpdateRequest;
import kr.co.axlink.dashboard.repository.DashboardRepository;
import kr.co.axlink.dashboard.repository.WidgetRepository;
import kr.co.axlink.semantic.service.SemanticQueryExecutor;
import kr.co.axlink.semantic.service.WidgetSpecValidator;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WidgetService {

  private final DashboardRepository dashboardRepository;
  private final WidgetRepository widgetRepository;
  private final JsonCodec jsonCodec;
  private final WidgetSpecValidator validator;
  private final SemanticQueryExecutor executor;
  private final DashboardService dashboardService;

  public WidgetService(DashboardRepository dashboardRepository, WidgetRepository widgetRepository,
      JsonCodec jsonCodec, WidgetSpecValidator validator, SemanticQueryExecutor executor,
      DashboardService dashboardService) {
    this.dashboardRepository = dashboardRepository;
    this.widgetRepository = widgetRepository;
    this.jsonCodec = jsonCodec;
    this.validator = validator;
    this.executor = executor;
    this.dashboardService = dashboardService;
  }

  @Transactional
  public WidgetResponse create(UUID dashboardId, WidgetCreateRequest req, AuthPrincipal principal) {
    Dashboard d = dashboardRepository.find(dashboardId)
        .orElseThrow(() -> ApiExceptions.notFound("dashboard", dashboardId));
    dashboardService.requireEditable(d, principal);
    validator.validate(req.spec(), principal);
    String specJson = jsonCodec.write(req.spec());
    UUID id = widgetRepository.create(dashboardId, req.spec().template(),
        req.spec().title(), specJson, principal.userId());
    if (req.gridItem() != null) {
      appendLayoutItem(d, req.gridItem(), id);
    }
    return toResponse(widgetRepository.find(id).orElseThrow());
  }

  @Transactional
  public WidgetResponse update(UUID widgetId, WidgetUpdateRequest req, AuthPrincipal principal) {
    Widget w = widgetRepository.find(widgetId)
        .orElseThrow(() -> ApiExceptions.notFound("widget", widgetId));
    Dashboard d = dashboardRepository.find(w.dashboardId())
        .orElseThrow(() -> ApiExceptions.notFound("dashboard", w.dashboardId()));
    dashboardService.requireEditable(d, principal);
    validator.validate(req.spec(), principal);
    String specJson = jsonCodec.write(req.spec());
    widgetRepository.update(widgetId, req.spec().template(), req.spec().title(), specJson);
    return toResponse(widgetRepository.find(widgetId).orElseThrow());
  }

  @Transactional
  public void delete(UUID widgetId, AuthPrincipal principal) {
    Widget w = widgetRepository.find(widgetId)
        .orElseThrow(() -> ApiExceptions.notFound("widget", widgetId));
    Dashboard d = dashboardRepository.find(w.dashboardId())
        .orElseThrow(() -> ApiExceptions.notFound("dashboard", w.dashboardId()));
    dashboardService.requireEditable(d, principal);
    widgetRepository.softDelete(widgetId);
    removeLayoutItem(d, widgetId);
  }

  /** 지운 위젯의 자리도 함께 뺀다 — 남겨 두면 빈 구멍이 생기고 저장할 때 다시 굳는다. */
  private void removeLayoutItem(Dashboard d, UUID widgetId) {
    kr.co.axlink.dashboard.dto.DashboardLayout layout =
        jsonCodec.read(d.layoutJson(), kr.co.axlink.dashboard.dto.DashboardLayout.class);
    if (layout == null) {
      return;
    }
    String key = widgetId.toString();
    kr.co.axlink.dashboard.dto.DashboardLayout updated =
        new kr.co.axlink.dashboard.dto.DashboardLayout(
            without(layout.lg(), key), without(layout.md(), key), without(layout.sm(), key));
    dashboardRepository.updateLayout(d.id(), jsonCodec.write(updated));
  }

  private static java.util.List<GridItem> without(java.util.List<GridItem> items, String key) {
    if (items == null) {
      return java.util.List.of();
    }
    return items.stream().filter(g -> !key.equals(g.i())).toList();
  }

  public WidgetDataResponse data(UUID widgetId, WidgetDataRequest req, AuthPrincipal principal) {
    Widget w = widgetRepository.find(widgetId)
        .orElseThrow(() -> ApiExceptions.notFound("widget", widgetId));
    WidgetSpec spec = jsonCodec.read(w.specJson(), WidgetSpec.class);
    return executor.run(spec, principal, req);
  }

  public WidgetDataResponse preview(WidgetSpec spec, AuthPrincipal principal) {
    return executor.run(spec, principal, null);
  }

  private void appendLayoutItem(Dashboard d, GridItem item, UUID widgetId) {
    kr.co.axlink.dashboard.dto.DashboardLayout layout =
        jsonCodec.read(d.layoutJson(), kr.co.axlink.dashboard.dto.DashboardLayout.class);
    GridItem withId = new GridItem(widgetId.toString(), item.x(), item.y(), item.w(), item.h(),
        item.minW(), item.minH());
    var lg = new java.util.ArrayList<>(layout.lg() == null ? java.util.List.of() : layout.lg());
    lg.add(withId);
    kr.co.axlink.dashboard.dto.DashboardLayout updated = new kr.co.axlink.dashboard.dto.DashboardLayout(
        lg, layout.md(), layout.sm());
    dashboardRepository.updateLayout(d.id(), jsonCodec.write(updated));
  }

  private WidgetResponse toResponse(Widget w) {
    return new WidgetResponse(
        w.id(),
        w.dashboardId(),
        w.template().name(),
        w.title(),
        jsonCodec.read(w.specJson(), WidgetSpec.class),
        w.createdAt(),
        w.updatedAt());
  }
}
