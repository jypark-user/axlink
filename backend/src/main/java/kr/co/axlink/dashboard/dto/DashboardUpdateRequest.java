package kr.co.axlink.dashboard.dto;

import jakarta.validation.constraints.NotBlank;

public record DashboardUpdateRequest(@NotBlank String name) {
}
