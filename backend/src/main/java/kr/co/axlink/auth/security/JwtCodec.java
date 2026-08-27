package kr.co.axlink.auth.security;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import kr.co.axlink.common.error.ApiExceptions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class JwtCodec {

  private static final Logger log = LoggerFactory.getLogger(JwtCodec.class);
  private static final String HEADER =
      encode("{\"alg\":\"HS256\",\"typ\":\"JWT\"}".getBytes(StandardCharsets.UTF_8));
  private static final Base64.Decoder DECODER = Base64.getUrlDecoder();
  private static final TypeReference<Map<String, Object>> CLAIMS =
      new TypeReference<Map<String, Object>>() {
      };

  private final byte[] key;
  private final ObjectMapper objectMapper;

  public JwtCodec(JwtProperties properties, ObjectMapper objectMapper) {
    this.key = resolveSecret(properties.secret());
    this.objectMapper = objectMapper;
  }

  public String sign(Map<String, Object> claims) {
    try {
      String payload = encode(objectMapper.writeValueAsBytes(claims));
      String signingInput = HEADER + "." + payload;
      return signingInput + "." + encode(hmac(signingInput));
    } catch (Exception e) {
      throw ApiExceptions.internal("토큰 발급에 실패했습니다.");
    }
  }

  public Map<String, Object> verify(String token) {
    String[] parts = token == null ? new String[0] : token.split("\\.");
    if (parts.length != 3) {
      throw ApiExceptions.tokenInvalid();
    }
    byte[] expected = hmac(parts[0] + "." + parts[1]);
    byte[] actual;
    Map<String, Object> claims;
    try {
      actual = DECODER.decode(parts[2]);
      claims = objectMapper.readValue(DECODER.decode(parts[1]), CLAIMS);
    } catch (Exception e) {
      throw ApiExceptions.tokenInvalid();
    }
    if (!MessageDigest.isEqual(expected, actual)) {
      throw ApiExceptions.tokenInvalid();
    }
    Object exp = claims.get("exp");
    if (!(exp instanceof Number expiresAt)) {
      throw ApiExceptions.tokenInvalid();
    }
    if (Instant.ofEpochSecond(expiresAt.longValue()).isBefore(Instant.now())) {
      throw ApiExceptions.tokenExpired();
    }
    return claims;
  }

  private byte[] hmac(String signingInput) {
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(key, "HmacSHA256"));
      return mac.doFinal(signingInput.getBytes(StandardCharsets.UTF_8));
    } catch (Exception e) {
      throw ApiExceptions.internal("토큰 서명에 실패했습니다.");
    }
  }

  private static String encode(byte[] bytes) {
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }

  private static byte[] resolveSecret(String secret) {
    if (secret == null || secret.isBlank()) {
      log.warn("axlink.security.jwt.secret 이 없어 일회용 서명키를 생성한다. "
          + "재기동하면 발급된 토큰이 모두 무효가 된다. 운영에서는 AXLINK_JWT_SECRET 를 설정하라.");
      byte[] generated = new byte[32];
      new SecureRandom().nextBytes(generated);
      return generated;
    }
    byte[] bytes = secret.getBytes(StandardCharsets.UTF_8);
    if (bytes.length < 32) {
      throw new IllegalStateException("axlink.security.jwt.secret 은 32바이트 이상이어야 한다.");
    }
    return bytes;
  }
}
