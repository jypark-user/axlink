package kr.co.axlink.rag.repository;

import java.util.Collection;
import java.util.UUID;

public final class SqlLiterals {

  private SqlLiterals() {}

  public static String uuidArray(Collection<UUID> ids) {
    if (ids == null || ids.isEmpty()) {
      return "array[]::uuid[]";
    }
    StringBuilder sb = new StringBuilder("array[");
    boolean first = true;
    for (UUID id : ids) {
      if (!first) {
        sb.append(',');
      }
      sb.append('\'').append(id.toString()).append("'::uuid");
      first = false;
    }
    sb.append(']');
    return sb.toString();
  }
}
