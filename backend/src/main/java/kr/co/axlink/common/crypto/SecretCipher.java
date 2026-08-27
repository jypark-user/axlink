package kr.co.axlink.common.crypto;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import kr.co.axlink.common.error.ApiExceptions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class SecretCipher {

  private static final Logger log = LoggerFactory.getLogger(SecretCipher.class);
  private static final int IV_BYTES = 12;
  private static final int TAG_BITS = 128;
  private static final int KEY_BYTES = 32;

  private final SecretKey key;
  private final SecureRandom random = new SecureRandom();

  public SecretCipher(CryptoProperties properties) {
    this.key = new SecretKeySpec(resolveKey(properties.masterKey()), "AES");
  }

  public String encrypt(String plain) {
    if (plain == null) {
      return null;
    }
    try {
      byte[] iv = new byte[IV_BYTES];
      random.nextBytes(iv);
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
      byte[] sealed = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
      byte[] out = new byte[iv.length + sealed.length];
      System.arraycopy(iv, 0, out, 0, iv.length);
      System.arraycopy(sealed, 0, out, iv.length, sealed.length);
      return Base64.getEncoder().encodeToString(out);
    } catch (Exception e) {
      throw ApiExceptions.internal("자격증명 암호화에 실패했습니다.");
    }
  }

  public String decrypt(String encoded) {
    if (encoded == null) {
      return null;
    }
    try {
      byte[] all = Base64.getDecoder().decode(encoded);
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, all, 0, IV_BYTES));
      byte[] plain = cipher.doFinal(all, IV_BYTES, all.length - IV_BYTES);
      return new String(plain, StandardCharsets.UTF_8);
    } catch (Exception e) {
      throw ApiExceptions.internal("자격증명 복호화에 실패했습니다.");
    }
  }

  public static String hint(String plain) {
    if (plain == null || plain.isBlank()) {
      return "****";
    }
    String tail = plain.length() <= 4 ? plain : plain.substring(plain.length() - 4);
    return "****" + tail;
  }

  private static byte[] resolveKey(String masterKey) {
    if (masterKey == null || masterKey.isBlank()) {
      log.warn("axlink.crypto.master-key 가 없어 일회용 키를 생성한다. "
          + "재기동하면 기존 암호문을 복호화할 수 없다. 운영에서는 AXLINK_SECRET_KEY 를 설정하라.");
      byte[] generated = new byte[KEY_BYTES];
      new SecureRandom().nextBytes(generated);
      return generated;
    }
    byte[] decoded = Base64.getDecoder().decode(masterKey);
    if (decoded.length != KEY_BYTES) {
      throw new IllegalStateException("axlink.crypto.master-key 는 Base64 32바이트여야 한다.");
    }
    return decoded;
  }
}
