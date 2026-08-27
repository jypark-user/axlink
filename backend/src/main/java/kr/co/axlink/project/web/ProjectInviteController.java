package kr.co.axlink.project.web;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.service.InviteService;
import kr.co.axlink.auth.web.InviteDtos.InviteResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/projects/{projectId}/invites")
public class ProjectInviteController {

  private final InviteService inviteService;

  public ProjectInviteController(InviteService inviteService) {
    this.inviteService = inviteService;
  }

  @PostMapping
  @PreAuthorize("hasRole('CLIENT')")
  public ResponseEntity<InviteResponse> create(@PathVariable UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(inviteService.create(projectId, principal));
  }

  @DeleteMapping("/{inviteId}")
  @PreAuthorize("hasRole('CLIENT')")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void revoke(@PathVariable UUID projectId, @PathVariable UUID inviteId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    inviteService.revoke(projectId, inviteId, principal);
  }
}
