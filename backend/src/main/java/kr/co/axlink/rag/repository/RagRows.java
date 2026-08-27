package kr.co.axlink.rag.repository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import kr.co.axlink.rag.domain.DocSourceType;
import kr.co.axlink.rag.domain.MessageFeedback;
import kr.co.axlink.rag.domain.MessageRole;
import kr.co.axlink.rag.domain.MessageStatus;
import kr.co.axlink.rag.domain.QueryRouteType;

public final class RagRows {

  private RagRows() {}

  public record ConversationRow(
      UUID id,
      UUID userId,
      String title,
      List<UUID> projectScope,
      boolean pinned,
      String status,
      Instant lastMessageAt,
      Instant createdAt) {}

  public record MessageRow(
      UUID id,
      UUID conversationId,
      int seq,
      MessageRole role,
      String content,
      MessageStatus status,
      QueryRouteType routeType,
      String rewrittenQuery,
      String measureKey,
      MessageFeedback feedback,
      Integer latencyMs,
      Instant createdAt,
      /** 생성 시점 인포그래픽 스냅샷. 원본 JSON 문자열이며 없으면 null. */
      String infographicJson) {}

  public record MessageSourceRow(
      UUID id,
      UUID messageId,
      int footnoteNo,
      UUID docChunkId,
      DocSourceType sourceType,
      UUID sourceId,
      UUID projectId,
      String projectName,
      String sourceTitle,
      String snippet,
      String externalUrl,
      Integer pageNo) {}
}
