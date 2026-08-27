package kr.co.axlink.rag.dto;

import java.util.List;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.rag.domain.QueryRouteType;

public record QueryRouting(
    QueryRouteType type,
    String rewrittenQuery,
    String measureKey,
    List<String> dimensions,
    /**
     * 모델이 고른 인포그래픽 형태. 어디까지나 희망이고, 데이터 모양과 맞지 않으면
     * 서버가 무시한다. 고르지 않았거나 그림이 불필요하면 null.
     */
    WidgetTemplate viz) {

  public static QueryRouting document(String rewrittenQuery) {
    return new QueryRouting(QueryRouteType.DOCUMENT, rewrittenQuery, null, List.of(), null);
  }
}
