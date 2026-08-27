package kr.co.axlink.project.web;

import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.project.service.AssignmentService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/projects/{projectId}/assignments")
public class AssignmentController {

  private final AssignmentService assignmentService;

  public AssignmentController(AssignmentService assignmentService) {
    this.assignmentService = assignmentService;
  }

  @GetMapping
  @PreAuthorize("hasRole('CLIENT')")
  public List<AssignmentResponse> list(@PathVariable UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return assignmentService.list(projectId, principal);
  }

  @PostMapping
  @PreAuthorize("hasRole('CLIENT')")
  public ResponseEntity<List<AssignmentResponse>> assign(@PathVariable UUID projectId,
      @Valid @RequestBody AssignmentCreateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(assignmentService.assign(projectId, req, principal));
  }

  @DeleteMapping("/{assignmentId}")
  @PreAuthorize("hasRole('CLIENT')")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void revoke(@PathVariable UUID projectId, @PathVariable UUID assignmentId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    assignmentService.revoke(projectId, assignmentId, principal);
  }
}
