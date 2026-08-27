package kr.co.axlink.rag.dto;

import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;

/**
 * 답변에 딸리는 인포그래픽. 값은 시맨틱 레이어가 DB 에서 뽑은 것이고,
 * 모델은 어떤 지표·차원을 볼지만 골랐다. 모델이 수치를 쓰지 않는다.
 */
public record SseInfographicEvent(
    WidgetTemplate template,
    String title,
    WidgetDataResponse data) {
}
