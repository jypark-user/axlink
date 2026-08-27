package kr.co.axlink.standard.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;

public final class RowReaders {

  private RowReaders() {}

  public static OffsetDateTime utc(Instant instant) {
    return instant == null ? null : instant.atOffset(ZoneOffset.UTC);
  }

  public static Instant instant(ResultSet rs, String col) throws SQLException {
    OffsetDateTime ts = rs.getObject(col, OffsetDateTime.class);
    return ts == null ? null : ts.toInstant();
  }

  public static LocalDate date(ResultSet rs, String col) throws SQLException {
    return rs.getObject(col, LocalDate.class);
  }

  public static UUID uuid(ResultSet rs, String col) throws SQLException {
    return rs.getObject(col, UUID.class);
  }

  public static UUID uuidNullable(ResultSet rs, String col) throws SQLException {
    Object v = rs.getObject(col);
    return v == null ? null : UUID.fromString(String.valueOf(v));
  }

  public static String str(ResultSet rs, String col) throws SQLException {
    return rs.getString(col);
  }

  public static boolean bool(ResultSet rs, String col) throws SQLException {
    return rs.getBoolean(col);
  }

  public static double dbl(ResultSet rs, String col) throws SQLException {
    return rs.getDouble(col);
  }

  public static <E extends Enum<E>> E en(ResultSet rs, String col, Class<E> type) throws SQLException {
    String v = rs.getString(col);
    return v == null ? null : Enum.valueOf(type, v);
  }
}
