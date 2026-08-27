package kr.co.axlink.ai.adapter.fake;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import kr.co.axlink.ai.port.EmbeddingPort;

public class FakeEmbeddingAdapter implements EmbeddingPort {

  private static final int DIMENSION = 1024;

  @Override
  public List<float[]> embed(List<String> texts) {
    List<float[]> vectors = new ArrayList<>(texts.size());
    for (String text : texts) {
      vectors.add(vectorOf(text));
    }
    return vectors;
  }

  @Override
  public int dimension() {
    return DIMENSION;
  }

  private static float[] vectorOf(String text) {
    Random random = new Random(seedOf(text));
    float[] vector = new float[DIMENSION];
    double sumOfSquares = 0.0;
    for (int i = 0; i < DIMENSION; i++) {
      vector[i] = (float) random.nextGaussian();
      sumOfSquares += (double) vector[i] * vector[i];
    }
    double norm = Math.sqrt(sumOfSquares);
    if (norm == 0.0) {
      vector[0] = 1.0f;
      return vector;
    }
    for (int i = 0; i < DIMENSION; i++) {
      vector[i] = (float) (vector[i] / norm);
    }
    return vector;
  }

  private static long seedOf(String text) {
    byte[] digest = sha256(text == null ? "" : text);
    long seed = 0L;
    for (int i = 0; i < 8; i++) {
      seed = (seed << 8) | (digest[i] & 0xFFL);
    }
    return seed;
  }

  private static byte[] sha256(String text) {
    try {
      return MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 is required", e);
    }
  }
}
