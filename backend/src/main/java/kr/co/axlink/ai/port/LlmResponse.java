package kr.co.axlink.ai.port;

public record LlmResponse(String text, String model, int promptTokens, int completionTokens) {}
