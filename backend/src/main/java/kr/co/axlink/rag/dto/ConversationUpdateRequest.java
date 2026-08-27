package kr.co.axlink.rag.dto;

import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;

public record ConversationUpdateRequest(
    @Size(max = 200) String title,
    Boolean pinned,
    List<UUID> projectScope) {
}
