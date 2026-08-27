package kr.co.axlink.rag.dto;

import java.util.List;

public record SseSourcesEvent(List<MessageSourceResponse> sources) {}
