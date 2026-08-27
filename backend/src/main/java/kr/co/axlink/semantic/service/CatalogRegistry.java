package kr.co.axlink.semantic.service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.FilterDef;
import kr.co.axlink.semantic.domain.FilterOp;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.repository.SemanticCatalogRepository;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class CatalogRegistry {

  private final SemanticCatalogRepository repository;
  private Map<String, MeasureDef> measures = Map.of();
  private Map<String, DimensionDef> dimensions = Map.of();
  private Map<String, FilterDef> filters = Map.of();

  public CatalogRegistry(SemanticCatalogRepository repository) {
    this.repository = repository;
  }

  @EventListener(ApplicationReadyEvent.class)
  public void load() {
    List<MeasureDef> measureList = repository.findActiveMeasures();
    List<DimensionDef> dimensionList = repository.findActiveDimensions();
    List<FilterDef> filterList = repository.findActiveFilters();

    if (measureList.isEmpty() || dimensionList.isEmpty() || filterList.isEmpty()) {
      throw new IllegalStateException("시맨틱 카탈로그 로드에 실패했습니다: 행이 비어 있습니다.");
    }

    Map<String, MeasureDef> measureMap = new LinkedHashMap<>();
    for (MeasureDef m : measureList) {
      measureMap.put(m.key(), m);
    }
    Map<String, DimensionDef> dimensionMap = new LinkedHashMap<>();
    for (DimensionDef d : dimensionList) {
      dimensionMap.put(d.key(), d);
    }
    Map<String, FilterDef> filterMap = new LinkedHashMap<>();
    for (FilterDef f : filterList) {
      filterMap.put(f.key(), f);
    }

    for (MeasureDef m : measureList) {
      for (String dimKey : m.allowedDimensions()) {
        if (!dimensionMap.containsKey(dimKey)) {
          throw new IllegalStateException(
              "시맨틱 카탈로그 참조 무결성 깨짐: measure=" + m.key()
                  + " 가 없는 dimension=" + dimKey + " 을 참조합니다.");
        }
      }
      for (String filterKey : m.allowedFilters()) {
        if (!filterMap.containsKey(filterKey)) {
          throw new IllegalStateException(
              "시맨틱 카탈로그 참조 무결성 깨짐: measure=" + m.key()
                  + " 가 없는 filter=" + filterKey + " 을 참조합니다.");
        }
      }
    }

    this.measures = Map.copyOf(measureMap);
    this.dimensions = Map.copyOf(dimensionMap);
    this.filters = Map.copyOf(filterMap);
  }

  public Optional<MeasureDef> measure(String key) {
    return Optional.ofNullable(measures.get(key));
  }

  public Optional<DimensionDef> dimension(String key) {
    return Optional.ofNullable(dimensions.get(key));
  }

  public Optional<FilterDef> filter(String field, FilterOp op) {
    return Optional.ofNullable(filters.get(FilterDef.keyOf(field, op)));
  }

  public List<MeasureDef> activeMeasures() {
    return List.copyOf(measures.values());
  }

  public List<DimensionDef> activeDimensions() {
    return List.copyOf(dimensions.values());
  }

  public List<FilterDef> activeFilters() {
    return List.copyOf(filters.values());
  }
}
