package kr.co.axlink.integration;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.co.axlink.integration.port.WorkProductType;
import org.junit.jupiter.api.Test;

class WorkProductTypeSchemaTest {

  private static final Pattern QUOTED = Pattern.compile("'([A-Z_]+)'");

  @Test
  void javaEnumMatchesCheckConstraintExactly() throws IOException {
    List<String> fromSql = checkConstraintValues("ck_work_product__type check (type in (");
    assertThat(fromSql).hasSize(22);
    assertThat(enumNames()).containsExactlyInAnyOrderElementsOf(fromSql);
  }

  @Test
  void javaEnumMatchesSemanticFilterEnumValues() throws IOException {
    List<String> fromSql =
        arrayLiteralValues("('work_product_type__in', 'work_product_type', 'IN',");
    assertThat(enumNames()).containsExactlyInAnyOrderElementsOf(fromSql);
  }

  private List<String> enumNames() {
    return Arrays.stream(WorkProductType.values()).map(Enum::name).toList();
  }

  private List<String> checkConstraintValues(String anchor) throws IOException {
    String block = sliceAfter(anchor, "))");
    List<String> values = new ArrayList<>();
    Matcher matcher = QUOTED.matcher(block);
    while (matcher.find()) {
      values.add(matcher.group(1));
    }
    return values;
  }

  private List<String> arrayLiteralValues(String anchor) throws IOException {
    String sql = readMigration();
    int start = sql.indexOf(anchor);
    assertThat(start).as("앵커를 찾지 못했습니다: " + anchor).isGreaterThan(0);
    int open = sql.indexOf('{', start);
    int close = sql.indexOf('}', open);
    return Arrays.stream(sql.substring(open + 1, close).split(","))
        .map(String::trim)
        .filter(token -> !token.isEmpty())
        .toList();
  }

  private String sliceAfter(String anchor, String terminator) throws IOException {
    String sql = readMigration();
    int start = sql.indexOf(anchor);
    assertThat(start).as("앵커를 찾지 못했습니다: " + anchor).isGreaterThan(0);
    int from = start + anchor.length();
    return sql.substring(from, sql.indexOf(terminator, from));
  }

  private String readMigration() throws IOException {
    try (InputStream in = getClass().getClassLoader()
        .getResourceAsStream("db/migration/V1__init.sql")) {
      assertThat(in).as("V1__init.sql 을 클래스패스에서 찾지 못했습니다.").isNotNull();
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    }
  }
}
