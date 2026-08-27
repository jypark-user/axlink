package kr.co.axlink.org.web;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;
import kr.co.axlink.org.domain.Role;

public record UserCreateRequest(
    @NotNull UUID organizationId,
    @Email @NotBlank String email,
    @NotBlank String name,
    @NotNull Role role) {
}
