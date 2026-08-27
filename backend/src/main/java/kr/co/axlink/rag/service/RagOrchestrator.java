package kr.co.axlink.rag.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.ai.port.EmbeddingPort;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmModels;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.config.AxLinkProperties;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetDataResponse;
import kr.co.axlink.dashboard.dto.WidgetRow;
import kr.co.axlink.rag.domain.AskContext;
import kr.co.axlink.rag.domain.MessageStatus;
import kr.co.axlink.rag.domain.ProcessedAnswer;
import kr.co.axlink.rag.domain.RetrievalSet;
import kr.co.axlink.rag.dto.MessageSourceResponse;
import kr.co.axlink.rag.dto.QueryRouting;
import kr.co.axlink.rag.dto.SseDoneEvent;
import kr.co.axlink.rag.dto.SseInfographicEvent;
import kr.co.axlink.rag.dto.SseStartEvent;
import kr.co.axlink.rag.repository.ConversationRepository;
import kr.co.axlink.rag.repository.RagRows.MessageSourceRow;
import kr.co.axlink.semantic.domain.AggregateContext;
import kr.co.axlink.semantic.dto.WidgetColumn;
import kr.co.axlink.semantic.service.SemanticQueryExecutor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class RagOrchestrator {

  private static final Logger log = LoggerFactory.getLogger(RagOrchestrator.class);
  private static final String NO_EVIDENCE_TEXT = "제공된 자료에서 확인할 수 없습니다.";

  private final QueryRouter queryRouter;
  private final EmbeddingPort embeddingPort;
  private final HybridSearchService hybridSearchService;
  private final ContextAssembler contextAssembler;
  private final AnswerPostProcessor answerPostProcessor;
  private final LlmPort llmPort;
  private final LlmModels llmModels;
  private final ConversationRepository conversationRepository;
  private final SemanticQueryExecutor semanticQueryExecutor;
  private final AxLinkProperties.Rag ragProps;

  public RagOrchestrator(QueryRouter queryRouter, EmbeddingPort embeddingPort,
      HybridSearchService hybridSearchService, ContextAssembler contextAssembler,
      AnswerPostProcessor answerPostProcessor, LlmPort llmPort, LlmModels llmModels,
      ConversationRepository conversationRepository, SemanticQueryExecutor semanticQueryExecutor,
      AxLinkProperties properties) {
    this.queryRouter = queryRouter;
    this.embeddingPort = embeddingPort;
    this.hybridSearchService = hybridSearchService;
    this.contextAssembler = contextAssembler;
    this.answerPostProcessor = answerPostProcessor;
    this.llmPort = llmPort;
    this.llmModels = llmModels;
    this.conversationRepository = conversationRepository;
    this.semanticQueryExecutor = semanticQueryExecutor;
    this.ragProps = properties.rag();
  }

  public void ask(AskContext ctx, SseSink sink) {
    long started = System.currentTimeMillis();
    try {
      QueryRouting routing = queryRouter.route(ctx.question(), ctx.history());
      RetrievalSet retrieval = retrieve(ctx, routing);
      sink.start(new SseStartEvent(ctx.conversationId(), ctx.userMessageId(),
          ctx.assistantMessageId(), routing, retrieval.size()));
      if (retrieval.isEmpty()) {
        sink.delta(NO_EVIDENCE_TEXT);
        sink.sources(List.of());
        sink.done(new SseDoneEvent(ctx.assistantMessageId(), "no_evidence",
            System.currentTimeMillis() - started));
        return;
      }
      // 수치는 모델이 쓰지 않는다 — 라우터가 고른 지표를 DB 에 돌려 그 값을 근거로 넘긴다.
      AggregateContext aggregate = aggregate(ctx, routing);
      List<LlmMessage> messages = contextAssembler.assemble(retrieval, formatAggregate(aggregate),
          routing, ctx.history(), ctx.question());
      LlmRequest request = LlmRequest.of(llmModels.synthesis(), messages);
      StringBuilder raw = new StringBuilder();
      llmPort.stream(request, delta -> {
        if (sink.isClosed()) {
          throw new AbortException();
        }
        if (delta.text() != null && !delta.text().isEmpty()) {
          raw.append(delta.text());
          sink.delta(delta.text());
        }
      });
      if (sink.isClosed()) {
        return;
      }
      ProcessedAnswer processed = answerPostProcessor.process(raw.toString(), retrieval);
      List<MessageSourceResponse> sourceResponses = toSourceResponses(processed, ctx);
      List<MessageSourceRow> sourceRows = toSourceRows(processed, ctx);
      // 저장과 전송이 같은 스냅샷을 쓰도록 먼저 만든다 — 새로고침 후에도 같은 그림이 나온다.
      SseInfographicEvent info = aggregate == null ? null
          : infographic(aggregate, routing.viz()).orElse(null);
      conversationRepository.insertAssistant(ctx.assistantMessageId(), ctx.conversationId(),
          assistantSeq(ctx), processed.text(), MessageStatus.COMPLETE,
          routing.type(), routing.rewrittenQuery(), routing.measureKey(),
          (int) (System.currentTimeMillis() - started), sourceRows, info);
      sink.sources(sourceResponses);
      if (info != null) {
        sink.infographic(info);
      }
      sink.done(new SseDoneEvent(ctx.assistantMessageId(), processed.finishReason(),
          System.currentTimeMillis() - started));
    } catch (AbortException e) {
      log.debug("stream aborted by client for conversation {}", ctx.conversationId());
    } catch (RuntimeException e) {
      log.warn("ask failed for conversation {}: {}", ctx.conversationId(), e.getMessage());
      sink.error(e);
    }
  }

  /**
   * 집계 결과를 어떤 그래프로 낼지 정한다. 모델이 아니라 데이터 모양이 고른다.
   * 큰 숫자 카드는 쓰지 않는다 — 값 하나는 문장이 이미 말하고 있다.
   * 위에서부터 먼저 맞는 규칙 하나가 이긴다.
   */
  // 같은 패키지의 RagOrchestratorInfographicTest 가 직접 부른다.
  static Optional<SseInfographicEvent> infographic(AggregateContext aggregate,
      WidgetTemplate suggested) {
    WidgetDataResponse data = aggregate.data();
    List<String> dims = aggregate.dimensions();
    int rows = data == null ? 0 : data.rows().size();
    // 축이 없으면 점 하나뿐이라 그릴 것이 없다.
    if (data == null || dims.isEmpty() || rows < 2) {
      return Optional.empty();
    }
    boolean percent = isRatioUnit(data.unit() == null ? "" : data.unit());
    boolean negative = hasNegative(data);
    WidgetTemplate template;
    if (fits(suggested, dims, rows, percent, negative)) {
      return Optional.of(new SseInfographicEvent(suggested, data.measureLabel(), data));
    }
    if (dims.size() >= 2) {
      if (isTimeDimension(dims.get(0)) && isStatusDimension(dims.get(1))) {
        // 기간 위의 상태 — 쌓이는 속도와 닫히는 속도가 벌어지는지가 요점이다.
        template = WidgetTemplate.CUMULATIVE_FLOW;
      } else if (isTimeDimension(dims.get(0))) {
        template = WidgetTemplate.AREA_CHART;
      } else if (rows > 40) {
        template = WidgetTemplate.HEATMAP;
      } else {
        template = WidgetTemplate.STACKED_BAR_CHART;
      }
    } else if (isDayDimension(dims.get(0))) {
      // 날짜 축은 눈금이 촘촘해 선으로는 빈 날이 안 보인다.
      template = WidgetTemplate.CALENDAR_HEATMAP;
    } else if (isTimeDimension(dims.get(0))) {
      template = rows > 12 ? WidgetTemplate.AREA_CHART : WidgetTemplate.LINE_CHART;
    } else if (isStatusDimension(dims.get(0))) {
      template = WidgetTemplate.STATUS_FLOW;
    } else if (percent && data.target() != null) {
      // 목표가 있는 비율은 목표선을 함께 봐야 좋은지 나쁜지 말이 된다.
      template = WidgetTemplate.BULLET_CHART;
    } else if (percent && rows <= 8) {
      template = WidgetTemplate.RADAR_CHART;
    } else if (rows <= 3 && !negative) {
      template = WidgetTemplate.PIE_CHART;
    } else if (rows <= 6 && !negative) {
      // 음수가 섞이면 원은 못 쓴다 — fits() 에서 거부한 그림으로 되돌아가지 않게 여기서도 막는다.
      template = WidgetTemplate.DONUT_CHART;
    } else if (rows <= 12) {
      template = WidgetTemplate.BAR_CHART;
    } else if (rows <= 25) {
      // 건수가 열 몇 갈래로 흩어지면 길이보다 "어디에 몰렸나" 가 답이다.
      template = percent ? WidgetTemplate.HORIZONTAL_BAR_CHART : WidgetTemplate.PARETO;
    } else if (rows <= 60) {
      // 25줄 넘으면 막대는 읽히지 않는다. 넓이로 보면 큰 덩어리는 보인다.
      template = WidgetTemplate.TREEMAP;
    } else {
      template = WidgetTemplate.DATA_TABLE;
    }
    return Optional.of(new SseInfographicEvent(template, data.measureLabel(), data));
  }

  /** 값에 음수가 섞였는지. 파이·도넛은 각도가 음수를 표현하지 못한다. */
  private static boolean hasNegative(WidgetDataResponse data) {
    return data.rows().stream()
        .map(r -> r.values().get("value"))
        .filter(Number.class::isInstance)
        .anyMatch(v -> ((Number) v).doubleValue() < 0);
  }

  /** 합산이 무의미한 비율 지표인지. 비율은 더해도 뜻이 없다. */
  private static boolean isRatioUnit(String unit) {
    return unit.contains("%") || unit.contains("율") || unit.contains("률");
  }

  /**
   * 모델이 고른 그림을 그대로 써도 되는지. 축 개수와 항목 수가 맞을 때만 존중한다 —
   * 데이터가 두 축인데 원그래프를 고르는 식의 실수를 막는다.
   */
  private static boolean fits(WidgetTemplate viz, List<String> dims, int rows, boolean percent,
      boolean negative) {
    if (viz == null || viz == WidgetTemplate.STAT_CARD) {
      return false;
    }
    return switch (viz) {
      // 음수 조각은 원에 그릴 수 없다 — 각도가 뜻을 잃는다.
      case PIE_CHART, DONUT_CHART -> dims.size() == 1 && rows <= 6 && !negative;
      case LINE_CHART, AREA_CHART -> dims.size() == 1;
      // 이행률 목록은 0~100 사이 비율이라야 막대 길이가 뜻을 가진다. 건수는 채울 목표가 없다.
      case PROGRESS_LIST -> dims.size() == 1 && percent;
      case BAR_CHART, HORIZONTAL_BAR_CHART, RADAR_CHART, STATUS_FLOW -> dims.size() == 1;
      case STACKED_BAR_CHART, HEATMAP -> dims.size() == 2;
      // 누적 흐름·순위 변화·기울기는 기간 축 위에 계열이 하나 더 있어야 뜻이 산다.
      case CUMULATIVE_FLOW, BUMP_CHART, SLOPE_CHART -> dims.size() == 2;
      case TREEMAP, SPARKLINE -> !dims.isEmpty();
      case PARETO -> dims.size() == 1 && rows >= 3;
      case CALENDAR_HEATMAP, BULLET_CHART -> dims.size() == 1;
      case DATA_TABLE -> true;
      default -> false;
    };
  }

  private static boolean isTimeDimension(String key) {
    String k = key.toLowerCase();
    return k.contains("date") || k.contains("month") || k.contains("week") || k.contains("day")
        || k.contains("period") || k.contains("quarter") || k.contains("year");
  }

  /** 날짜 눈금 축 — 달력이 맞다. 주·월은 선으로도 읽힌다. */
  private static boolean isDayDimension(String key) {
    String k = key.toLowerCase();
    return k.contains("day") || k.contains("date");
  }

  /** 단계별로 몇 건이 걸려 있는지 보는 축 — 100% 누적 띠가 맞다. */
  private static boolean isStatusDimension(String key) {
    String k = key.toLowerCase();
    return k.contains("status") || k.contains("phase") || k.contains("stage");
  }

  /** 라우터가 지표를 고른 질의만 집계한다. 실패하면 문서 근거만으로 답한다. */
  private AggregateContext aggregate(AskContext ctx, QueryRouting routing) {
    if (routing.measureKey() == null || ctx.projectScope() == null || ctx.projectScope().isEmpty()) {
      return null;
    }
    try {
      return semanticQueryExecutor.runForRag(routing.measureKey(), routing.dimensions(), List.of(),
          Set.copyOf(ctx.projectScope()));
    } catch (RuntimeException e) {
      log.warn("aggregate for measure {} failed: {}", routing.measureKey(), e.getMessage());
      return null;
    }
  }

  /** 집계 결과를 프롬프트에 넣을 표로 편다. 이 값이 답변 수치의 유일한 출처다. */
  /**
   * 집계 결과를 모델이 읽을 수 있는 글로 적는다. 원시 행은 컬럼 이름이 {@code d0} 라
   * 모델이 무엇을 본 것인지 알 수 없고 합계도 없어서, 비중·최댓값 같은 질문에
   * "자료에 없다"고 답해버린다. 이미 계산된 표 메타데이터를 그대로 쓴다.
   */
  private static String formatAggregate(AggregateContext aggregate) {
    if (aggregate == null || aggregate.rows().isEmpty()) {
      return null;
    }
    WidgetDataResponse data = aggregate.data();
    if (data == null) {
      return null;
    }
    String unit = data.unit() == null ? "" : data.unit();
    StringBuilder out = new StringBuilder("지표: ").append(data.measureLabel());
    if (!unit.isEmpty()) {
      out.append(" (단위: ").append(unit).append(')');
    }
    out.append('\n');

    // 차원 값에 사람이 읽는 이름이 따로 있으면 그것을 쓴다. 없으면 원래 값이 곧 이름이다.
    // 프로젝트처럼 select_expr 이 UUID 인 차원은 d0 를 그대로 쓰면 답변에 UUID 가 나온다.
    boolean hasLabel = data.columns().stream().anyMatch(c -> "d0_label".equals(c.key()));
    String valueKey = hasLabel ? "d0_label" : "d0";
    String dimensionLabel = data.columns().stream()
        .filter(c -> !"value".equals(c.key()) && !"d0_label".equals(c.key()))
        .map(WidgetColumn::label).findFirst().orElse(null);
    double sum = 0;
    boolean numeric = true;
    for (WidgetRow row : data.rows()) {
      Object value = row.values().get("value");
      Object key = dimensionLabel == null ? null : row.values().get(valueKey);
      out.append("- ");
      if (key != null) {
        out.append(dimensionLabel).append(' ').append(key).append(": ");
      }
      out.append(value).append(unit).append('\n');
      if (value instanceof Number n) {
        sum += n.doubleValue();
      } else {
        numeric = false;
      }
    }
    // 합계를 주지 않으면 모델이 비중을 낼 수 없다. 합산이 무의미한 비율 지표는 뺀다.
    if (numeric && data.rows().size() > 1 && !isRatioUnit(unit)) {
      out.append("합계: ").append(trim(sum)).append(unit).append('\n');
    }
    if (data.total() != null) {
      out.append("전체: ").append(data.total().values().get("value")).append(unit).append('\n');
    }
    return out.toString();
  }

  private static String trim(double v) {
    return v == Math.rint(v) ? String.valueOf((long) v) : String.valueOf(v);
  }

  private RetrievalSet retrieve(AskContext ctx, QueryRouting routing) {
    if (ctx.projectScope() == null || ctx.projectScope().isEmpty()) {
      return RetrievalSet.EMPTY;
    }
    float[] queryVector = embeddingPort.embed(List.of(routing.rewrittenQuery())).get(0);
    return hybridSearchService.search(queryVector, routing.rewrittenQuery(),
        ctx.projectScope(), ragProps.vectorTopK(), ragProps.fusedTopK());
  }

  private int assistantSeq(AskContext ctx) {
    return conversationRepository.nextSeq(ctx.conversationId());
  }

  private List<MessageSourceResponse> toSourceResponses(ProcessedAnswer processed, AskContext ctx) {
    List<MessageSourceResponse> result = new ArrayList<>();
    for (ProcessedAnswer.SourceRef ref : processed.sources()) {
      var chunk = ref.chunk();
      result.add(new MessageSourceResponse(ref.footnoteNo(), chunk.id(),
          chunk.sourceType().name(), chunk.sourceId(), chunk.sourceTitle(),
          chunk.projectId(), null, ref.snippet(), chunk.sourceUri(), null, chunk.pageNo()));
    }
    return result;
  }

  private List<MessageSourceRow> toSourceRows(ProcessedAnswer processed, AskContext ctx) {
    List<MessageSourceRow> rows = new ArrayList<>();
    for (ProcessedAnswer.SourceRef ref : processed.sources()) {
      var chunk = ref.chunk();
      rows.add(new MessageSourceRow(UUID.randomUUID(), ctx.assistantMessageId(),
          ref.footnoteNo(), chunk.id(), chunk.sourceType(), chunk.sourceId(),
          chunk.projectId(), null, chunk.sourceTitle(), ref.snippet(),
          chunk.sourceUri(), chunk.pageNo()));
    }
    return rows;
  }

  private static final class AbortException extends RuntimeException {
    AbortException() {
      super("client aborted", null, false, false);
    }
  }
}
