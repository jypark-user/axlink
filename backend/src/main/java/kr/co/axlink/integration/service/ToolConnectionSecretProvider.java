package kr.co.axlink.integration.service;

import java.util.Map;
import java.util.Optional;
import kr.co.axlink.common.crypto.SecretCipher;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolCredential;
import org.springframework.stereotype.Component;

@Component
public class ToolConnectionSecretProvider {

  private final SecretCipher secretCipher;
  private final JsonCodec jsonCodec;

  public ToolConnectionSecretProvider(SecretCipher secretCipher, JsonCodec jsonCodec) {
    this.secretCipher = secretCipher;
    this.jsonCodec = jsonCodec;
  }

  public ToolCredential decrypt(ToolConnection connection) {
    String json = secretCipher.decrypt(connection.authEncrypted());
    Map<String, String> parsed = jsonCodec.read(json,
        new com.fasterxml.jackson.core.type.TypeReference<Map<String, String>>() {});
    String username = parsed == null ? null : parsed.get("username");
    String secret = parsed == null ? null : parsed.get("secret");
    return new ToolCredential(username, secret);
  }

  public String encrypt(ToolCredential credential) {
    Map<String, String> map = new java.util.LinkedHashMap<>();
    map.put("username", credential.username());
    map.put("secret", credential.secret());
    return secretCipher.encrypt(jsonCodec.write(map));
  }

  public String hint(ToolCredential credential) {
    return SecretCipher.hint(credential.secret());
  }

  Optional<String> secretHint(ToolConnection connection) {
    return Optional.ofNullable(connection.authHint());
  }
}
