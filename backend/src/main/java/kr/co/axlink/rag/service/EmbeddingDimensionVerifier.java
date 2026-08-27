package kr.co.axlink.rag.service;

import kr.co.axlink.ai.port.EmbeddingPort;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class EmbeddingDimensionVerifier {

  private static final Logger log = LoggerFactory.getLogger(EmbeddingDimensionVerifier.class);

  private final JdbcClient jdbc;
  private final EmbeddingPort embeddingPort;

  public EmbeddingDimensionVerifier(JdbcClient jdbc, EmbeddingPort embeddingPort) {
    this.jdbc = jdbc;
    this.embeddingPort = embeddingPort;
  }

  @EventListener(ApplicationReadyEvent.class)
  public void verify() {
    Integer columnDimension = jdbc.sql("""
        select atttypmod from pg_attribute
         where attrelid = 'doc_chunk'::regclass and attname = 'embedding'
        """).query(Integer.class).optional().orElse(-1);
    int declared = embeddingPort.dimension();
    if (columnDimension < 0) {
      log.warn("doc_chunk.embedding column not found; skipping dimension check");
      return;
    }
    if (columnDimension != declared) {
      throw new IllegalStateException(
          "doc_chunk.embedding dimension " + columnDimension + " != EmbeddingPort.dimension() "
              + declared + " (INV-29)");
    }
    log.info("embedding dimension verified: {}", declared);
  }
}
