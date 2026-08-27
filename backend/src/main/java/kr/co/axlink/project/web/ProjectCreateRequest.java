package kr.co.axlink.project.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;

public record ProjectCreateRequest(
    @NotBlank String name,
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate,
    @NotBlank String description,
    String contractorName,
    /** 이 사업을 지울 때 맞춰야 하는 비밀번호. 해시로만 저장한다. */
    @NotBlank @Size(min = 4, max = 72) String deletePassword) {
}
