package kr.co.axlink.rag.dto;

import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;

public record ConversationCreateRequest(
    @Size(max = 200) String title,
    List<UUID> projectScope) {
}
