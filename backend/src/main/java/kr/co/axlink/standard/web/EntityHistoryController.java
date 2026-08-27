package kr.co.axlink.standard.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.standard.domain.HistoryEntityType;
import kr.co.axlink.standard.history.EntityHistoryRepository;
import kr.co.axlink.standard.repository.StandardRows;
import kr.co.axlink.standard.web.StandardDtos.EntityHistoryResponse;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EntityHistoryController {

  private final EntityHistoryRepository entityHistoryRepository;

  public EntityHistoryController(EntityHistoryRepository entityHistoryRepository) {
    this.entityHistoryRepository = entityHistoryRepository;
  }

  @GetMapping("/api/entity-history")
  public PageResponse<EntityHistoryResponse> list(@RequestParam HistoryEntityType entityType,
      @RequestParam UUID entityId, PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    var rows = entityHistoryRepository.search(entityType, entityId, java.util.List.of(), page);
    long total = entityHistoryRepository.count(entityType, entityId);
    return PageResponse.of(rows.stream().map(EntityHistoryController::toResponse).toList(), page, total);
  }

  private static EntityHistoryResponse toResponse(StandardRows.EntityHistoryRow h) {
    return new EntityHistoryResponse(h.id(), h.entityType().name(), h.entityId(), h.field(),
        h.fromValue(), h.toValue(), h.actor(), null, h.changedAt());
  }
}
