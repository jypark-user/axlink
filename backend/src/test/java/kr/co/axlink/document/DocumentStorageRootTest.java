package kr.co.axlink.document;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ErrorCode;
import kr.co.axlink.config.AxLinkProperties;
import kr.co.axlink.document.service.DocumentStorage;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class DocumentStorageRootTest {

  private static DocumentStorage storageAt(String root) {
    return new DocumentStorage(new AxLinkProperties(null, null, null,
        new AxLinkProperties.Storage(root, 52428800L)));
  }

  @Test
  void storedFileIsResolvableWhenRootIsRelative(@TempDir Path tmp) {
    String root = tmp.resolve("./nested/../nested").toString();
    DocumentStorage storage = storageAt(root);
    UUID projectId = UUID.randomUUID();
    String stored = storage.store(projectId, "DOCX",
        new ByteArrayInputStream("hello".getBytes(StandardCharsets.UTF_8)));
    Path resolved = storage.pathOf(stored);
    assertTrue(Files.exists(resolved));
    assertTrue(storage.load(stored).exists());
  }

  @Test
  void traversalOutsideRootIsRejected(@TempDir Path tmp) {
    DocumentStorage storage = storageAt(tmp.toString());
    ApiException e = assertThrows(ApiException.class, () -> storage.pathOf("../escaped.docx"));
    assertEquals(ErrorCode.RESOURCE_NOT_FOUND, e.code());
  }
}
