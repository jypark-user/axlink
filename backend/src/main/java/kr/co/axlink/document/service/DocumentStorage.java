package kr.co.axlink.document.service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import kr.co.axlink.common.error.ApiExceptions;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class DocumentStorage {

  private final Path root;

  public DocumentStorage(kr.co.axlink.config.AxLinkProperties props) {
    this.root = Paths.get(props.storage().root()).toAbsolutePath().normalize();
  }

  public String store(UUID projectId, String ext, InputStream in) {
    Path dir = root.resolve(projectId.toString());
    try {
      Files.createDirectories(dir);
    } catch (IOException e) {
      throw ApiExceptions.internal("저장 디렉터리 생성 실패: " + e.getMessage());
    }
    String fileName = UUID.randomUUID() + "." + ext.toLowerCase();
    Path target = dir.resolve(fileName);
    try {
      Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING);
    } catch (IOException e) {
      throw ApiExceptions.internal("파일 저장 실패: " + e.getMessage());
    }
    return root.relativize(target).toString();
  }

  public Resource load(String storedPath) {
    Path resolved = root.resolve(storedPath).normalize();
    if (!resolved.startsWith(root)) {
      throw ApiExceptions.notFound("document", UUID.randomUUID());
    }
    Resource resource = new FileSystemResource(resolved);
    if (!resource.exists()) {
      throw ApiExceptions.notFound("document", UUID.randomUUID());
    }
    return resource;
  }

  public Path pathOf(String storedPath) {
    Path resolved = root.resolve(storedPath).normalize();
    if (!resolved.startsWith(root) || !Files.exists(resolved)) {
      throw ApiExceptions.notFound("document", UUID.randomUUID());
    }
    return resolved;
  }

  public void delete(String storedPath) {
    Path resolved = root.resolve(storedPath).normalize();
    if (!resolved.startsWith(root)) {
      return;
    }
    try {
      Files.deleteIfExists(resolved);
    } catch (IOException ignored) {
    }
  }
}
