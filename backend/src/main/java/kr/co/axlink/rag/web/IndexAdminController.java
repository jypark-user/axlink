package kr.co.axlink.rag.web;

import kr.co.axlink.rag.service.IndexingService;
import kr.co.axlink.rag.service.IndexingService.BackfillResult;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class IndexAdminController {

  private final IndexingService indexingService;

  public IndexAdminController(IndexingService indexingService) {
    this.indexingService = indexingService;
  }

  /** 전체 원천을 다시 색인한다. 임베딩 호출이 원천 수만큼 일어나므로 운영 중 남용 금지. */
  @PostMapping("/admin/index/backfill")
  @PreAuthorize("hasRole('SUPER_ADMIN')")
  public BackfillResult backfill() {
    return indexingService.backfill();
  }
}
