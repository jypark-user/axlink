package kr.co.axlink.semantic.web;

import java.util.List;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.FilterDef;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.dto.SemanticCatalogResponse;
import kr.co.axlink.semantic.dto.SemanticDimensionResponse;
import kr.co.axlink.semantic.dto.SemanticFilterResponse;
import kr.co.axlink.semantic.dto.SemanticMeasureResponse;
import kr.co.axlink.semantic.service.CatalogRegistry;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/semantic")
public class SemanticCatalogController {

  private final CatalogRegistry registry;

  public SemanticCatalogController(CatalogRegistry registry) {
    this.registry = registry;
  }

  @GetMapping("/catalog")
  public SemanticCatalogResponse catalog(@AuthenticationPrincipal AuthPrincipal principal) {
    requireCatalogAccess(principal);
    List<SemanticMeasureResponse> measures = registry.activeMeasures().stream()
        .map(SemanticCatalogController::toMeasure).toList();
    List<SemanticDimensionResponse> dimensions = registry.activeDimensions().stream()
        .map(SemanticCatalogController::toDimension).toList();
    List<SemanticFilterResponse> filters = registry.activeFilters().stream()
        .map(SemanticCatalogController::toFilter).toList();
    return new SemanticCatalogResponse(measures, dimensions, filters);
  }

  @GetMapping("/measures/{measureKey}")
  public SemanticMeasureResponse measure(@PathVariable String measureKey,
      @AuthenticationPrincipal AuthPrincipal principal) {
    requireCatalogAccess(principal);
    MeasureDef m = registry.measure(measureKey)
        .orElseThrow(() -> ApiExceptions.notFound("semantic_measure", java.util.UUID.randomUUID()));
    return toMeasure(m);
  }

  private static void requireCatalogAccess(AuthPrincipal principal) {
    if (principal == null) {
      throw ApiExceptions.roleForbidden();
    }
  }

  private static SemanticMeasureResponse toMeasure(MeasureDef m) {
    return new SemanticMeasureResponse(
        m.key(),
        m.label(),
        m.description(),
        m.unit(),
        List.copyOf(m.allowedDimensions()),
        List.copyOf(m.allowedFilters()),
        List.of(),
        m.status().name().toLowerCase(java.util.Locale.ROOT));
  }

  private static SemanticDimensionResponse toDimension(DimensionDef d) {
    return new SemanticDimensionResponse(
        d.key(),
        d.label(),
        d.description(),
        d.valueType().name().equals("TIME") ? "date" : "string",
        List.of(),
        d.status().name().toLowerCase(java.util.Locale.ROOT));
  }

  private static SemanticFilterResponse toFilter(FilterDef f) {
    return new SemanticFilterResponse(
        f.key(),
        f.field(),
        f.op().name().toLowerCase(java.util.Locale.ROOT),
        f.label(),
        f.valueType().name().toLowerCase(java.util.Locale.ROOT),
        f.enumValues() == null ? List.of() : List.copyOf(f.enumValues()),
        f.status().name().toLowerCase(java.util.Locale.ROOT));
  }
}
