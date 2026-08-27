package kr.co.axlink.rag.repository;

import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.rag.domain.AskContext;
import kr.co.axlink.rag.domain.DocSourceType;
import kr.co.axlink.rag.domain.MessageFeedback;
import kr.co.axlink.rag.domain.MessageRole;
import kr.co.axlink.rag.domain.MessageStatus;
import kr.co.axlink.rag.domain.QueryRouteType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class ConversationRepository {

  private final JdbcClient jdbc;
  private final JsonCodec json;

  /**
   * message 조회 컬럼. {@code mapMessage} 가 여기 있는 컬럼을 전부 읽으므로
   * 조회마다 따로 적으면 하나 빠졌을 때 런타임에야 터진다. 한 곳에서만 고친다.
   */
  private static final String MESSAGE_COLUMNS = """
      select id, conversation_id, seq, role, content, status, route_type,
             rewritten_query, measure_key, feedback, latency_ms, created_at,
             infographic_json
      """;

  public ConversationRepository(JdbcClient jdbc, JsonCodec json) {
    this.jdbc = jdbc;
    this.json = json;
  }

  public List<RagRows.ConversationRow> list(UUID userId, int offset, int limit) {
    return jdbc.sql("""
        select id, user_id, title, project_scope, pinned, status, last_message_at, created_at
          from conversation
         where user_id = :userId and status = 'ACTIVE'
         order by pinned desc, last_message_at desc nulls last, created_at desc
         limit :limit offset :offset
        """)
        .param("userId", userId)
        .param("limit", limit)
        .param("offset", offset)
        .query(this::mapConversation).list();
  }

  public long count(UUID userId) {
    return jdbc.sql("select count(*) from conversation where user_id = :userId and status = 'ACTIVE'")
        .param("userId", userId)
        .query(Long.class).single();
  }

  public Optional<RagRows.ConversationRow> find(UUID id) {
    return jdbc.sql("""
        select id, user_id, title, project_scope, pinned, status, last_message_at, created_at
          from conversation where id = :id
        """)
        .param("id", id)
        .query(this::mapConversation).optional();
  }

  public UUID create(UUID userId, String title, List<UUID> projectScope) {
    String scopeLiteral = SqlLiterals.uuidArray(projectScope);
    return jdbc.sql("""
        insert into conversation (user_id, title, project_scope)
        values (:userId, :title, """ + scopeLiteral + """
        )
        returning id
        """)
        .param("userId", userId)
        .param("title", title)
        .query(UUID.class).single();
  }

  public int update(UUID id, String title, Boolean pinned, List<UUID> projectScope) {
    return jdbc.sql("""
        update conversation
           set title = coalesce(:title, title),
               pinned = coalesce(:pinned, pinned),
               project_scope = """ + (projectScope == null ? "project_scope" : SqlLiterals.uuidArray(projectScope)) + """
              , updated_at = now()
         where id = :id
        """)
        .param("id", id)
        .param("title", title)
        .param("pinned", pinned)
        .update();
  }

  public int softDelete(UUID id) {
    return jdbc.sql("update conversation set status = 'DELETED', updated_at = now() where id = :id")
        .param("id", id).update();
  }

  public int messageCount(UUID conversationId) {
    return jdbc.sql("select count(*) from message where conversation_id = :id")
        .param("id", conversationId).query(Integer.class).single();
  }

  public List<String> projectNames(List<UUID> ids) {
    if (ids == null || ids.isEmpty()) {
      return List.of();
    }
    return jdbc.sql("select name from project where id = any(" + SqlLiterals.uuidArray(ids)
        + ") order by name")
        .query(String.class).list();
  }

  public int nextSeq(UUID conversationId) {
    Integer max = jdbc.sql("select max(seq) from message where conversation_id = :id")
        .param("id", conversationId).query(Integer.class).optional().orElse(0);
    return (max == null ? 0 : max) + 1;
  }

  public UUID insertUserMessage(UUID conversationId, int seq, String content) {
    return insertMessage(conversationId, seq, MessageRole.USER, content, MessageStatus.COMPLETE,
        null, null, null, null);
  }

  @Transactional
  public void insertAssistant(UUID messageId, UUID conversationId, int seq, String content,
      MessageStatus status, QueryRouteType route, String rewrittenQuery, String measureKey,
      Integer latencyMs, List<RagRows.MessageSourceRow> sources, Object infographic) {
    jdbc.sql("""
        insert into message (id, conversation_id, seq, role, content, status, route_type,
                             rewritten_query, measure_key, latency_ms, infographic_json)
        values (:id, :cid, :seq, 'ASSISTANT', :content, :status, :route, :rq, :mk, :lat,
                :info::jsonb)
        """)
        .param("id", messageId)
        .param("cid", conversationId)
        .param("seq", seq)
        .param("content", content)
        .param("status", status.name())
        .param("route", route == null ? null : route.name())
        .param("rq", rewrittenQuery)
        .param("mk", measureKey)
        .param("lat", latencyMs)
        .param("info", infographic == null ? null : json.write(infographic))
        .update();
    if (sources != null) {
      for (RagRows.MessageSourceRow s : sources) {
        insertSource(s);
      }
    }
    touchConversation(conversationId);
  }

  public int touchConversation(UUID conversationId) {
    return jdbc.sql("update conversation set last_message_at = now(), updated_at = now() where id = :id")
        .param("id", conversationId).update();
  }

  private UUID insertMessage(UUID conversationId, int seq, MessageRole role, String content,
      MessageStatus status, QueryRouteType route, String rq, String mk, Integer latency) {
    return jdbc.sql("""
        insert into message (conversation_id, seq, role, content, status, route_type,
                             rewritten_query, measure_key, latency_ms)
        values (:cid, :seq, :role, :content, :status, :route, :rq, :mk, :lat)
        returning id
        """)
        .param("cid", conversationId)
        .param("seq", seq)
        .param("role", role.name())
        .param("content", content)
        .param("status", status.name())
        .param("route", route == null ? null : route.name())
        .param("rq", rq)
        .param("mk", mk)
        .param("lat", latency)
        .query(UUID.class).single();
  }

  private void insertSource(RagRows.MessageSourceRow s) {
    jdbc.sql("""
        insert into message_source (message_id, footnote_no, doc_chunk_id, source_type,
                                    source_title, snippet, external_url, page_no)
        values (:mid, :fn, :dcid, :st, :stitle, :snip, :url, :pn)
        """)
        .param("mid", s.messageId())
        .param("fn", s.footnoteNo())
        .param("dcid", s.docChunkId())
        .param("st", s.sourceType().name())
        .param("stitle", s.sourceTitle())
        .param("snip", s.snippet())
        .param("url", s.externalUrl())
        .param("pn", s.pageNo())
        .update();
  }

  public List<RagRows.MessageRow> messages(UUID conversationId) {
    return jdbc.sql(MESSAGE_COLUMNS + """
          from message where conversation_id = :id order by seq
        """)
        .param("id", conversationId)
        .query(this::mapMessage).list();
  }

  public List<RagRows.MessageSourceRow> sources(UUID messageId) {
    return jdbc.sql(sourceSelect("where ms.message_id = :id order by ms.footnote_no"))
        .param("id", messageId)
        .query(this::mapSource).list();
  }

  public Map<UUID, List<RagRows.MessageSourceRow>> sourcesByMessage(List<UUID> messageIds) {
    if (messageIds.isEmpty()) {
      return Map.of();
    }
    Map<UUID, List<RagRows.MessageSourceRow>> result = new LinkedHashMap<>();
    jdbc.sql(sourceSelect(
        "where ms.message_id = any(" + SqlLiterals.uuidArray(messageIds)
            + ") order by ms.message_id, ms.footnote_no"))
        .query(this::mapSource).list()
        .forEach(s -> result.computeIfAbsent(s.messageId(), k -> new ArrayList<>()).add(s));
    return result;
  }

  private String sourceSelect(String tail) {
    return """
        select ms.id, ms.message_id, ms.footnote_no, ms.doc_chunk_id, ms.source_type,
               ms.source_title, ms.snippet, ms.external_url, ms.page_no,
               c.source_id, c.project_id, p.name as project_name
          from message_source ms
          left join doc_chunk c on c.id = ms.doc_chunk_id
          left join project p on p.id = c.project_id
        """ + tail;
  }

  public Optional<RagRows.MessageRow> findMessage(UUID id) {
    return jdbc.sql(MESSAGE_COLUMNS + """
          from message where id = :id
        """)
        .param("id", id).query(this::mapMessage).optional();
  }

  public int setFeedback(UUID messageId, MessageFeedback feedback) {
    return jdbc.sql("update message set feedback = :fb, updated_at = now() where id = :id")
        .param("id", messageId)
        .param("fb", feedback.name())
        .update();
  }

  public List<AskContext.Message> recentHistory(UUID conversationId, int turns) {
    List<RagRows.MessageRow> rows = jdbc.sql(MESSAGE_COLUMNS + """
          from message where conversation_id = :id and role = 'USER'
         order by seq desc limit :n
        """)
        .param("id", conversationId).param("n", turns)
        .query(this::mapMessage).list();
    List<AskContext.Message> result = new ArrayList<>();
    for (int i = rows.size() - 1; i >= 0; i--) {
      RagRows.MessageRow m = rows.get(i);
      result.add(new AskContext.Message(MessageRole.USER, m.content()));
    }
    return result;
  }

  private RagRows.ConversationRow mapConversation(ResultSet rs, int n) throws SQLException {
    return new RagRows.ConversationRow(
        rs.getObject("id", UUID.class),
        rs.getObject("user_id", UUID.class),
        rs.getString("title"),
        readUuidArray(rs.getArray("project_scope")),
        rs.getBoolean("pinned"),
        rs.getString("status"),
        rs.getTimestamp("last_message_at") == null ? null
            : rs.getTimestamp("last_message_at").toInstant(),
        rs.getTimestamp("created_at").toInstant());
  }

  private RagRows.MessageRow mapMessage(ResultSet rs, int n) throws SQLException {
    return new RagRows.MessageRow(
        rs.getObject("id", UUID.class),
        rs.getObject("conversation_id", UUID.class),
        rs.getInt("seq"),
        enumValue(rs.getString("role"), MessageRole.class),
        rs.getString("content"),
        enumValue(rs.getString("status"), MessageStatus.class),
        enumValue(rs.getString("route_type"), QueryRouteType.class),
        rs.getString("rewritten_query"),
        rs.getString("measure_key"),
        enumValue(rs.getString("feedback"), MessageFeedback.class),
        (Integer) rs.getObject("latency_ms"),
        rs.getTimestamp("created_at").toInstant(),
        rs.getString("infographic_json"));
  }

  private RagRows.MessageSourceRow mapSource(ResultSet rs, int n) throws SQLException {
    return new RagRows.MessageSourceRow(
        rs.getObject("id", UUID.class),
        rs.getObject("message_id", UUID.class),
        rs.getInt("footnote_no"),
        rs.getObject("doc_chunk_id", UUID.class),
        enumValue(rs.getString("source_type"), DocSourceType.class),
        rs.getObject("source_id", UUID.class),
        rs.getObject("project_id", UUID.class),
        rs.getString("project_name"),
        rs.getString("source_title"),
        rs.getString("snippet"),
        rs.getString("external_url"),
        (Integer) rs.getObject("page_no"));
  }

  private static <E extends Enum<E>> E enumValue(String value, Class<E> type) {
    return value == null ? null : Enum.valueOf(type, value);
  }

  private static List<UUID> readUuidArray(Array array) throws SQLException {
    if (array == null) {
      return List.of();
    }
    Object[] elements = (Object[]) array.getArray();
    List<UUID> result = new ArrayList<>(elements.length);
    for (Object element : elements) {
      result.add((UUID) element);
    }
    return result;
  }

  public void requireOwned(RagRows.ConversationRow c, UUID userId) {
    if (c == null) {
      throw ApiExceptions.notFound("conversation", null);
    }
    if (!c.userId().equals(userId)) {
      throw ApiExceptions.notFound("conversation", c.id());
    }
  }
}
