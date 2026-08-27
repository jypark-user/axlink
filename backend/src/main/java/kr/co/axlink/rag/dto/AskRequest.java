package kr.co.axlink.rag.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;

public record AskRequest(
    @NotBlank @Size(max = 4000) String question,
    List<UUID> projectScope) {
}
