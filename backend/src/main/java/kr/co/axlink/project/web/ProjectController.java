package kr.co.axlink.project.web;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.web.PageQuery;
import kr.co.axlink.common.web.PageResponse;
import kr.co.axlink.project.domain.ProjectStatus;
import kr.co.axlink.project.service.ProjectClosureService;
import kr.co.axlink.project.service.ProjectService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {

  private final ProjectService projectService;
  private final ProjectClosureService closureService;

  public ProjectController(ProjectService projectService, ProjectClosureService closureService) {
    this.projectService = projectService;
    this.closureService = closureService;
  }

  @GetMapping
  public PageResponse<ProjectSummaryResponse> list(
      @RequestParam(required = false) ProjectStatus status,
      @RequestParam(required = false) String q,
      PageQuery page,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return projectService.list(status, q, page, principal);
  }

  @PostMapping
  @PreAuthorize("hasRole('CLIENT')")
  public ResponseEntity<ProjectDetailResponse> create(@Valid @RequestBody ProjectCreateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(projectService.create(req, principal));
  }

  @GetMapping("/{projectId}")
  public ProjectDetailResponse get(@PathVariable UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return projectService.get(projectId, principal);
  }

  @PatchMapping("/{projectId}")
  @PreAuthorize("hasRole('CLIENT')")
  public ProjectDetailResponse update(@PathVariable UUID projectId,
      @Valid @RequestBody ProjectUpdateRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return projectService.update(projectId, req, principal);
  }

  /** 사업 삭제 — 등록할 때 정한 비밀번호를 맞춰야 지워진다. 하위 자료까지 함께 사라진다. */
  @DeleteMapping("/{projectId}")
  @PreAuthorize("hasRole('CLIENT')")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void delete(@PathVariable UUID projectId,
      @Valid @RequestBody ProjectDeleteRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    projectService.delete(projectId, req.password(), principal);
  }

  @GetMapping("/{projectId}/closure-check")
  @PreAuthorize("hasRole('CLIENT')")
  public ProjectClosureResponse closureCheck(@PathVariable UUID projectId,
      @AuthenticationPrincipal AuthPrincipal principal) {
    return closureService.check(projectId, principal);
  }

  @PostMapping("/{projectId}/close")
  @PreAuthorize("hasRole('CLIENT')")
  public ProjectDetailResponse close(@PathVariable UUID projectId,
      @Valid @RequestBody ProjectCloseRequest req,
      @AuthenticationPrincipal AuthPrincipal principal) {
    closureService.close(projectId, principal);
    return projectService.get(projectId, principal);
  }
}
