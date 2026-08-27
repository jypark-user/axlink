package kr.co.axlink.org.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import kr.co.axlink.org.domain.OrgType;

public record OrganizationCreateRequest(
    @NotBlank String name,
    @NotNull OrgType type,
    String businessNo) {
}
