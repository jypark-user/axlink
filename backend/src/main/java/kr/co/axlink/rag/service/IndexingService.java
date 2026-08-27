package kr.co.axlink.rag.service;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.ai.port.EmbeddingPort;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.rag.domain.ChunkDraft;
import kr.co.axlink.rag.domain.DocChunk;
import kr.co.axlink.rag.domain.DocSourceType;
import kr.co.axlink.rag.repository.DocChunkRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndexingService {

  private static final Logger log = LoggerFactory.getLogger(IndexingService.class);

  private final DocChunkRepository chunkRepository;
  private final ChunkingService chunkingService;
  private final EmbeddingPort embeddingPort;
  private final JsonCodec json;
  private final JdbcClient jdbc;

  public IndexingService(DocChunkRepository chunkRepository, ChunkingService chunkingService,
      EmbeddingPort embeddingPort, JsonCodec json, JdbcClient jdbc) {
    this.chunkRepository = chunkRepository;
    this.chunkingService = chunkingService;
    this.embeddingPort = embeddingPort;
    this.json = json;
    this.jdbc = jdbc;
  }

  @Transactional
  public int reindex(DocSourceType type, UUID sourceId, UUID projectId) {
    SourceContent content = loadSource(type, sourceId);
    if (content == null || content.body == null || content.body.isBlank()) {
      chunkRepository.deleteBySource(type, sourceId);
      return 0;
    }
    chunkRepository.deleteBySource(type, sourceId);
    List<ChunkDraft> drafts = chunkingService.chunk(type, content.title, content.body,
        content.meta);
    if (drafts.isEmpty()) {
      return 0;
    }
    List<String> texts = drafts.stream().map(ChunkDraft::content).toList();
    List<float[]> embeddings = embeddingPort.embed(texts);
    for (int i = 0; i < drafts.size(); i++) {
      ChunkDraft draft = drafts.get(i);
      DocChunk chunk = new DocChunk(
          UUID.randomUUID(), projectId, type, sourceId, i, draft.content(),
          "bge-m3",
          draft.tokenCount(), content.title, content.uri, draft.contentHash(), draft.meta());
      chunkRepository.insert(chunk, embeddings.get(i));
    }
    return drafts.size();
  }

  public int reindexAll(Map<DocSourceType, Set<UUID>> changed) {
    int total = 0;
    for (Map.Entry<DocSourceType, Set<UUID>> entry : changed.entrySet()) {
      for (UUID sourceId : entry.getValue()) {
        try {
          UUID projectId = projectIdOf(entry.getKey(), sourceId);
          if (projectId != null) {
            total += reindex(entry.getKey(), sourceId, projectId);
          }
        } catch (RuntimeException e) {
          log.warn("reindex failed for {} {}: {}", entry.getKey(), sourceId, e.getMessage());
        }
      }
    }
    return total;
  }

  public void deleteBySource(DocSourceType type, UUID sourceId) {
    chunkRepository.deleteBySource(type, sourceId);
  }

  /**
   * 전체 원천을 훑어 색인을 다시 만든다. 시드·마이그레이션으로 직접 적재돼 서비스 계층을 거치지
   * 않은 데이터가 검색되지 않는 문제를 되돌리기 위한 관리 작업이다. 본문이 빈 원천은 {@link
   * #reindex}가 0을 돌려주므로 자연히 건너뛴다.
   */
  public BackfillResult backfill() {
    Map<DocSourceType, Set<UUID>> all = new LinkedHashMap<>();
    for (DocSourceType type : DocSourceType.values()) {
      List<UUID> ids = jdbc.sql("select id from " + tableOf(type)).query(UUID.class).list();
      if (!ids.isEmpty()) {
        all.put(type, new LinkedHashSet<>(ids));
      }
    }
    int chunks = reindexAll(all);
    int orphans = deleteOrphans();
    int sources = all.values().stream().mapToInt(Set::size).sum();
    log.info("backfill done: sources={}, chunks={}, orphansDeleted={}", sources, chunks, orphans);
    return new BackfillResult(sources, chunks, orphans);
  }

  /** 원천 행이 사라진 청크를 지운다. 삭제가 서비스 계층 밖에서 일어나면 남는다. */
  private int deleteOrphans() {
    int deleted = 0;
    for (DocSourceType type : DocSourceType.values()) {
      deleted += jdbc.sql("delete from doc_chunk where source_type = :st"
              + " and source_id not in (select id from " + tableOf(type) + ")")
          .param("st", type.name()).update();
    }
    return deleted;
  }

  public record BackfillResult(int sources, int chunks, int orphansDeleted) {}

  private UUID projectIdOf(DocSourceType type, UUID sourceId) {
    return jdbc.sql("select project_id from " + tableOf(type) + " where id = :id")
        .param("id", sourceId).query(UUID.class).optional().orElse(null);
  }

  private SourceContent loadSource(DocSourceType type, UUID sourceId) {
    return switch (type) {
      case REQUIREMENT -> fetch(type, sourceId, "requirement",
          "select title, coalesce(body,'') as body, external_url from requirement where id = :id");
      case ISSUE -> fetch(type, sourceId, "issue",
          "select title, coalesce(body,'') as body, external_url from issue where id = :id");
      case RISK -> fetch(type, sourceId, "risk",
          "select title, coalesce(body,'') as body, external_url from risk where id = :id");
      case CHANGE_REQUEST -> fetch(type, sourceId, "change_request",
          "select title, coalesce(reason,'') as body, null as external_url from change_request where id = :id");
      case CORRECTION_ACTION -> fetch(type, sourceId, "correction_action",
          "select coalesce(finding,'') as title, coalesce(action,'') as body, null as external_url from correction_action where id = :id");
      case PROGRESS_RECORD -> fetch(type, sourceId, "progress_record",
          "select coalesce(summary,'') as title, '' as body, null as external_url from progress_record where id = :id");
      case MEETING_RECORD -> fetch(type, sourceId, "meeting_record",
          "select title, coalesce(minutes,'') as body, null as external_url from meeting_record where id = :id");
      case WORK_PRODUCT -> fetchWorkProduct(sourceId);
      case DOCUMENT_UPLOAD -> fetchDocument(sourceId);
    };
  }

  private SourceContent fetch(DocSourceType type, UUID sourceId, String table, String sql) {
    return jdbc.sql(sql).param("id", sourceId).query((rs, n) -> {
      String title = rs.getString("title");
      if (title == null || title.isBlank()) {
        title = table;
      }
      return new SourceContent(title, rs.getString("body"), rs.getString("external_url"), new HashMap<>());
    }).optional().orElse(null);
  }

  private SourceContent fetchWorkProduct(UUID sourceId) {
    return jdbc.sql("""
        select coalesce(title, type) as title, coalesce(file_uri,'') as body, external_url
          from work_product where id = :id
        """)
        .param("id", sourceId)
        .query((rs, n) -> new SourceContent(
            rs.getString("title"), rs.getString("body"), rs.getString("external_url"),
            new HashMap<>()))
        .optional().orElse(null);
  }

  private SourceContent fetchDocument(UUID sourceId) {
    return jdbc.sql("""
        select original_filename, coalesce(extracted_text,'') as body, null as external_url
          from document_upload where id = :id
        """)
        .param("id", sourceId)
        .query((rs, n) -> new SourceContent(
            rs.getString("original_filename"), rs.getString("body"), null, new HashMap<>()))
        .optional().orElse(null);
  }

  private static String tableOf(DocSourceType type) {
    return switch (type) {
      case WORK_PRODUCT -> "work_product";
      case REQUIREMENT -> "requirement";
      case ISSUE -> "issue";
      case RISK -> "risk";
      case CHANGE_REQUEST -> "change_request";
      case CORRECTION_ACTION -> "correction_action";
      case MEETING_RECORD -> "meeting_record";
      case PROGRESS_RECORD -> "progress_record";
      case DOCUMENT_UPLOAD -> "document_upload";
    };
  }

  record SourceContent(String title, String body, String uri, Map<String, Object> meta) {}
}
