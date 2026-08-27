package kr.co.axlink.rag.dto;

import jakarta.validation.constraints.NotNull;
import kr.co.axlink.rag.domain.MessageFeedback;

public record MessageFeedbackRequest(@NotNull MessageFeedback feedback) {
}
