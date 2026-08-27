package kr.co.axlink.dashboard.web;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.dashboard.dto.WidgetCreateRequest;
import kr.co.axlink.dashboard.dto.WidgetDataRequest;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetGenerateRequest;
import kr.co.axlink.dashboard.dto.WidgetGenerateResponse;
import kr.co.axlink.dashboard.dto.WidgetPreviewRequest;
import kr.co.axlink.dashboard.dto.WidgetResponse;
import kr.co.axlink.dashboard.dto.WidgetUpdateRequest;
import kr.co.axlink.dashboard.service.WidgetGenerationService;
import kr.co.axlink.dashboard.service.WidgetService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class WidgetController {

  private final WidgetService widgetService;
  private final WidgetGenerationService generationService;

  public WidgetController(WidgetService widgetService, WidgetGenerationService generationService) {
    this.widgetService = widgetService;
    this.generationService = generationService;
  }

  @PostMapping("/widgets/generate")
  public WidgetGenerateResponse generate(@Valid @RequestBody WidgetGenerateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return generationService.generate(req, principal);
  }

  @PostMapping("/widgets/preview")
  public WidgetDataResponse preview(@Valid @RequestBody WidgetPreviewRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return widgetService.preview(req.spec(), principal);
  }

  @PostMapping("/dashboards/{dashboardId}/widgets")
  public ResponseEntity<WidgetResponse> create(@PathVariable UUID dashboardId,
      @Valid @RequestBody WidgetCreateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    WidgetResponse body = widgetService.create(dashboardId, req, principal);
    return ResponseEntity.status(HttpStatus.CREATED).body(body);
  }

  @PatchMapping("/widgets/{widgetId}")
  public WidgetResponse update(@PathVariable UUID widgetId,
      @Valid @RequestBody WidgetUpdateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return widgetService.update(widgetId, req, principal);
  }

  @DeleteMapping("/widgets/{widgetId}")
  public ResponseEntity<Void> delete(@PathVariable UUID widgetId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    widgetService.delete(widgetId, principal);
    return ResponseEntity.noContent().build();
  }

  @PostMapping("/widgets/{widgetId}/data")
  public WidgetDataResponse data(@PathVariable UUID widgetId,
      @RequestBody(required = false) WidgetDataRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return widgetService.data(widgetId, req, principal);
  }
}
