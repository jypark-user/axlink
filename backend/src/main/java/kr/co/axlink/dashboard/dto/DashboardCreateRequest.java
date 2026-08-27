package kr.co.axlink.dashboard.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.UUID;

public record DashboardCreateRequest(
    @NotBlank String name,
    UUID projectId) {
}
