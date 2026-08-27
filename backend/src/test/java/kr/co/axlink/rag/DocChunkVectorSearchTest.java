package kr.co.axlink.rag;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.ai.port.EmbeddingPort;
import kr.co.axlink.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;

@Transactional
class DocChunkVectorSearchTest extends AbstractIntegrationTest {

  @Autowired
  private JdbcClient jdbcClient;
  @Autowired
  private EmbeddingPort embeddingPort;

  @Test
  void fakeEmbeddingsLoadAsPgvectorAndCosineOrderPutsExactMatchFirst() {
    List<String> texts = List.of(
        "요구사항 이행률은 82퍼센트입니다.",
        "형상관리 커밋 활동량이 지난달보다 늘었습니다.",
        "시정조치 3건이 기한을 넘겼습니다.");
    for (int i = 0; i < texts.size(); i++) {
      insertChunk(i, texts.get(i));
    }

    float[] query = embeddingPort.embed(List.of(texts.get(2))).get(0);
    List<Map<String, Object>> ranked = jdbcClient.sql("""
        select content, embedding <=> cast(:query as vector) as distance
          from doc_chunk
         where project_id = :projectId
         order by distance
         limit 3
        """)
        .param("query", toVectorLiteral(query))
        .param("projectId", SEED_PROJECT_ID)
        .query()
        .listOfRows();

    assertThat(ranked).hasSize(3);
    assertThat(ranked.get(0).get("content")).isEqualTo(texts.get(2));
    assertThat(((Number) ranked.get(0).get("distance")).doubleValue()).isLessThan(1e-6);
    double first = ((Number) ranked.get(0).get("distance")).doubleValue();
    double last = ((Number) ranked.get(2).get("distance")).doubleValue();
    assertThat(first).isLessThan(last);
  }

  @Test
  void generatedTsvectorSupportsFullTextSearch() {
    insertChunk(0, "변경요청 승인 절차와 인수기록 발급 기준");
    insertChunk(1, "코드 리뷰 체크리스트");

    List<String> hits = jdbcClient.sql("""
        select content from doc_chunk
         where project_id = :projectId
           and content_tsv @@ plainto_tsquery('simple', :q)
        """)
        .param("projectId", SEED_PROJECT_ID)
        .param("q", "인수기록")
        .query(String.class)
        .list();

    assertThat(hits).hasSize(1);
    assertThat(hits.get(0)).contains("인수기록");
  }

  @Test
  void embeddingDimensionMismatchIsRejectedByTheColumnType() {
    org.assertj.core.api.Assertions.assertThatThrownBy(() -> jdbcClient.sql("""
        insert into doc_chunk (project_id, source_type, source_id, chunk_index, content,
                               embedding, source_title, source_uri, content_hash)
        values (:projectId, 'DOCUMENT_UPLOAD', :sourceId, 99, '차원 불일치',
                cast('[1,2,3]' as vector), '제목', 'axlink://test', :hash)
        """)
        .param("projectId", SEED_PROJECT_ID)
        .param("sourceId", UUID.randomUUID())
        .param("hash", "0".repeat(64))
        .update()).isInstanceOf(RuntimeException.class);
  }

  private void insertChunk(int index, String content) {
    float[] vector = embeddingPort.embed(List.of(content)).get(0);
    assertThat(vector).hasSize(1024);
    jdbcClient.sql("""
        insert into doc_chunk (project_id, source_type, source_id, chunk_index, content,
                               embedding, embedding_model, source_title, source_uri, content_hash)
        values (:projectId, 'DOCUMENT_UPLOAD', :sourceId, :index, :content,
                cast(:embedding as vector), 'fake', :title, :uri, :hash)
        """)
        .param("projectId", SEED_PROJECT_ID)
        .param("sourceId", UUID.nameUUIDFromBytes(("chunk-" + index).getBytes()))
        .param("index", index)
        .param("content", content)
        .param("embedding", toVectorLiteral(vector))
        .param("title", "테스트 문서 " + index)
        .param("uri", "axlink://test/" + index)
        .param("hash", String.format("%064d", index))
        .update();
  }

  private String toVectorLiteral(float[] vector) {
    StringBuilder sb = new StringBuilder("[");
    for (int i = 0; i < vector.length; i++) {
      if (i > 0) {
        sb.append(',');
      }
      sb.append(vector[i]);
    }
    return sb.append(']').toString();
  }
}
