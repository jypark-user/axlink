package kr.co.axlink.project.web;

import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.UUID;

public record AssignmentCreateRequest(
    @NotNull UUID contractorOrgId,
    @NotEmpty List<UUID> userIds) {
}
