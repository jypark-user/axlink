package kr.co.axlink.semantic.service;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetFilter;
import kr.co.axlink.dashboard.dto.WidgetOptions;
import kr.co.axlink.dashboard.dto.WidgetQuery;
import kr.co.axlink.dashboard.dto.WidgetSpec;
import kr.co.axlink.semantic.domain.BoundFilter;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.FilterDef;
import kr.co.axlink.semantic.domain.FilterOp;
import kr.co.axlink.semantic.domain.FilterValueType;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.domain.ValidatedSpec;
import org.springframework.stereotype.Component;

@Component
public class WidgetSpecValidator {

  private final CatalogRegistry registry;
  private final ProjectAccessResolver accessResolver;

  public WidgetSpecValidator(CatalogRegistry registry, ProjectAccessResolver accessResolver) {
    this.registry = registry;
    this.accessResolver = accessResolver;
  }

  public ValidatedSpec validate(WidgetSpec spec, AuthPrincipal principal) {
    return validate(spec, accessResolver.allowedProjectIds(principal));
  }

  public ValidatedSpec validate(WidgetSpec spec, Set<UUID> allowedProjectIds) {
    if (spec == null) {
      throw ApiExceptions.validationFailed("WidgetSpec 이 비어 있습니다.");
    }
    if (spec.template() == null) {
      throw ApiExceptions.validationFailed("template 이 지정되지 않았습니다.");
    }
    WidgetTemplate template = spec.template();
    if (!isValidTemplate(template)) {
      throw ApiExceptions.validationFailed("알 수 없는 위젯 템플릿: " + template);
    }
    WidgetQuery query = spec.query();
    if (query == null || query.measure() == null) {
      throw ApiExceptions.validationFailed("query.measure 가 필요합니다.");
    }
    MeasureDef measure = registry.measure(query.measure())
        .orElseThrow(() -> ApiExceptions.catalogValidationFailed(
            "알 수 없는 measure: " + query.measure()));

    List<DimensionDef> dims = new ArrayList<>();
    if (query.dimensions() != null) {
      for (String dimKey : query.dimensions()) {
        if (!measure.allowedDimensions().contains(dimKey)) {
          throw ApiExceptions.catalogValidationFailed(
              "measure 가 허용하지 않는 dimension: " + dimKey);
        }
        DimensionDef d = registry.dimension(dimKey)
            .orElseThrow(() -> ApiExceptions.catalogValidationFailed(
                "알 수 없는 dimension: " + dimKey));
        dims.add(d);
      }
    }
    if (dims.size() > 2) {
      throw ApiExceptions.validationFailed("dimension 은 최대 2개입니다.");
    }

    List<BoundFilter> boundFilters = new ArrayList<>();
    if (query.filters() != null) {
      for (WidgetFilter f : query.filters()) {
        FilterOp op = FilterOp.parse(f.op());
        if (op == null) {
          throw ApiExceptions.catalogValidationFailed("알 수 없는 filter op: " + f.op());
        }
        String filterKey = FilterDef.keyOf(f.field(), op);
        if (!measure.allowedFilters().contains(filterKey)) {
          throw ApiExceptions.catalogValidationFailed(
              "measure 가 허용하지 않는 filter: " + filterKey);
        }
        FilterDef def = registry.filter(f.field(), op)
            .orElseThrow(() -> ApiExceptions.catalogValidationFailed(
                "알 수 없는 filter: " + filterKey));
        validateValue(def, f);
        boundFilters.add(new BoundFilter(def, extractValues(f)));
      }
    }
    if (boundFilters.size() > 5) {
      throw ApiExceptions.validationFailed("filter 는 최대 5개입니다.");
    }

    Set<UUID> projectIds = resolveProjectScope(allowedProjectIds, query.projectScope());

    WidgetOptions options = spec.options() == null
        ? new WidgetOptions(null, null, null, null, null, null, null)
        : spec.options();
    Integer limit = resolveLimit(template, query.limit());

    return new ValidatedSpec(template, spec.title(), measure, dims, boundFilters,
        projectIds, options, limit);
  }

  private boolean isValidTemplate(WidgetTemplate t) {
    try {
      WidgetTemplate.valueOf(t.name());
      return true;
    } catch (IllegalArgumentException e) {
      return false;
    }
  }

  private void validateValue(FilterDef def, WidgetFilter filter) {
    List<Object> values = extractValues(filter);
    if (def.valueType() == FilterValueType.ENUM_LIST) {
      for (Object v : values) {
        if (!def.enumValues().contains(String.valueOf(v))) {
          throw ApiExceptions.catalogValidationFailed(
              "enum 값이 허용 목록에 없습니다: " + v + " (field=" + def.field() + ")");
        }
      }
    } else if (def.valueType() == FilterValueType.UUID_LIST) {
      for (Object v : values) {
        try {
          UUID.fromString(String.valueOf(v));
        } catch (IllegalArgumentException e) {
          throw ApiExceptions.catalogValidationFailed("UUID 값이 올바르지 않습니다: " + v);
        }
      }
    } else if (def.valueType() == FilterValueType.INT) {
      for (Object v : values) {
        try {
          Integer.parseInt(String.valueOf(v));
        } catch (NumberFormatException e) {
          throw ApiExceptions.catalogValidationFailed("정수 값이 올바르지 않습니다: " + v);
        }
      }
    } else if (def.valueType() == FilterValueType.DATE_RANGE) {
      if (values.size() != 2) {
        throw ApiExceptions.catalogValidationFailed("DATE_RANGE 필터는 값 2개가 필요합니다.");
      }
    } else if (def.valueType() == FilterValueType.MONTH_TOKEN) {
      // token = "current" or "YYYY-MM"; validated at bind time
    }
  }

  private Set<UUID> resolveProjectScope(Set<UUID> allowed, Collection<UUID> requested) {
    if (requested == null || requested.isEmpty()) {
      return allowed;
    }
    Set<UUID> intersection = new LinkedHashSet<>(requested);
    intersection.retainAll(allowed);
    if (intersection.isEmpty()) {
      throw ApiExceptions.projectAccessDenied();
    }
    return intersection;
  }

  private Integer resolveLimit(WidgetTemplate template, Integer requested) {
    int defaultLimit = 50;
    int cap = (template == WidgetTemplate.DATA_TABLE || template == WidgetTemplate.PROGRESS_LIST)
        ? 100 : 20;
    int resolved = requested == null ? defaultLimit : requested;
    return Math.min(resolved, cap);
  }

  private List<Object> extractValues(WidgetFilter filter) {
    Object raw = filter.value();
    if (raw instanceof List<?> list) {
      return list.stream().map(v -> (Object) v).toList();
    }
    return List.of(raw);
  }
}
