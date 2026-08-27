package kr.co.axlink.project.web;

import java.time.LocalDate;
import kr.co.axlink.project.domain.SiPhase;

public record ProjectUpdateRequest(
    String name,
    LocalDate startDate,
    LocalDate endDate,
    String description,
    String contractorName,
    SiPhase currentSiPhase) {
}
