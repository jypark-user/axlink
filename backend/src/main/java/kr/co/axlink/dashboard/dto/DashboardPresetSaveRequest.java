package kr.co.axlink.dashboard.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;

/** 지금 보고 있는 대시보드를 이름 붙여 저장한다. */
public record DashboardPresetSaveRequest(
    @NotBlank @Size(max = 100) String name,
    @NotNull UUID dashboardId) {
}
