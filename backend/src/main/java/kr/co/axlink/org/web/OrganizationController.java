package kr.co.axlink.org.web;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.service.OrganizationService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/organizations")
public class OrganizationController {

  private final OrganizationService organizationService;

  public OrganizationController(OrganizationService organizationService) {
    this.organizationService = organizationService;
  }

  @GetMapping
  public PageResponse<OrganizationResponse> list(
      @RequestParam(required = false) OrgType type,
      @RequestParam(required = false) String q,
      PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return organizationService.list(type, q, page);
  }

  @PostMapping
  @PreAuthorize("hasRole('SUPER_ADMIN')")
  public ResponseEntity<OrganizationResponse> create(@Valid @RequestBody OrganizationCreateRequest req) {
    return ResponseEntity.status(HttpStatus.CREATED).body(organizationService.create(req));
  }

  @GetMapping("/{organizationId}")
  public OrganizationResponse get(@PathVariable UUID organizationId) {
    return organizationService.get(organizationId);
  }

  @PatchMapping("/{organizationId}")
  @PreAuthorize("hasRole('SUPER_ADMIN')")
  public OrganizationResponse update(@PathVariable UUID organizationId,
      @Valid @RequestBody OrganizationUpdateRequest req) {
    return organizationService.update(organizationId, req);
  }
}
