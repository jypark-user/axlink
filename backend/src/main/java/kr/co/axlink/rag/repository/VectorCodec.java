package kr.co.axlink.rag.repository;

import java.util.Locale;

public final class VectorCodec {

  private VectorCodec() {}

  public static String toLiteral(float[] v) {
    StringBuilder sb = new StringBuilder(v.length * 10 + 2);
    sb.append('[');
    for (int i = 0; i < v.length; i++) {
      if (i > 0) {
        sb.append(',');
      }
      sb.append(String.format(Locale.ROOT, "%.6f", v[i]));
    }
    sb.append(']');
    return sb.toString();
  }

  public static float[] fromString(String s) {
    if (s == null || s.isBlank()) {
      return new float[0];
    }
    String body = s.startsWith("[") ? s.substring(1, s.length() - 1) : s;
    String[] parts = body.split(",");
    float[] result = new float[parts.length];
    for (int i = 0; i < parts.length; i++) {
      result[i] = Float.parseFloat(parts[i].trim());
    }
    return result;
  }
}
