package kr.co.axlink.semantic;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import kr.co.axlink.dashboard.domain.WidgetTemplate;
import kr.co.axlink.dashboard.dto.WidgetOptions;
import kr.co.axlink.semantic.domain.CatalogStatus;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.DimensionValueType;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.domain.MeasureValueType;
import kr.co.axlink.semantic.domain.ValidatedSpec;
import kr.co.axlink.semantic.service.SemanticQueryBuilder;
import kr.co.axlink.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.simple.JdbcClient;

class SemanticJoinDedupeTest extends AbstractIntegrationTest {

  @Autowired
  private SemanticQueryBuilder builder;

  @Autowired
  private JdbcClient jdbcClient;

  @Test
  void sameAliasJoinedByDifferentClauseTextIsEmittedOnce() {
    ValidatedSpec spec = specWith(
        "join project p on p.id = e.project_id",
        "LEFT JOIN project p ON e.project_id = p.id",
        null);

    SemanticQueryBuilder.BuiltQuery built = builder.build(spec);
    assertThat(occurrences(built.sql(), "join project p"))
        .as("같은 별칭 p 를 다른 문구로 조인해도 join 은 한 번만 나와야 한다: %s", built.sql())
        .isEqualTo(1);
    assertThatCode(() -> execute(built))
        .as("중복 별칭이 남으면 Postgres 가 실행 시점에 거부한다: %s", built.sql())
        .doesNotThrowAnyException();
  }

  @Test
  void multiJoinClauseIsSplitAndDedupedPerAlias() {
    ValidatedSpec spec = specWith(
        "join project p on p.id = e.project_id",
        "join project p on p.id = e.project_id left join organization o on o.id = p.client_org_id",
        "left join organization o on o.id = p.client_org_id");

    SemanticQueryBuilder.BuiltQuery built = builder.build(spec);
    assertThat(occurrences(built.sql(), "join project p"))
        .as("여러 조인이 붙은 절도 별칭 단위로 쪼개져 중복 제거되어야 한다: %s", built.sql())
        .isEqualTo(1);
    assertThat(occurrences(built.sql(), "join organization o"))
        .as("두 번째 별칭 o 도 한 번만 나와야 한다: %s", built.sql())
        .isEqualTo(1);
    assertThatCode(() -> execute(built)).doesNotThrowAnyException();
  }

  @Test
  void distinctAliasesOnSameTableAreBothKept() {
    ValidatedSpec spec = specWith(
        "join project p on p.id = e.project_id",
        "join project p2 on p2.id = e.project_id",
        null);

    SemanticQueryBuilder.BuiltQuery built = builder.build(spec);
    assertThat(occurrences(built.sql(), "join project p2"))
        .as("별칭이 다르면 같은 테이블이라도 둘 다 남아야 한다: %s", built.sql())
        .isEqualTo(1);
    assertThat(built.sql()).contains("join project p on");
    assertThatCode(() -> execute(built)).doesNotThrowAnyException();
  }

  private ValidatedSpec specWith(String measureJoin, String dimensionJoin, String secondDimJoin) {
    MeasureDef measure = new MeasureDef(
        UUID.randomUUID(), "join_dedupe_probe", "조인 중복 검증", null, "issue", measureJoin,
        null, "count(*)", MeasureValueType.COUNT, "건", Set.of(), Set.of(), null, null,
        CatalogStatus.ACTIVE);
    DimensionDef first = new DimensionDef(
        UUID.randomUUID(), "probe_project", "프로젝트", null, "e.project_id::text", "p.name",
        dimensionJoin, DimensionValueType.CATEGORY, CatalogStatus.ACTIVE);
    List<DimensionDef> dimensions = secondDimJoin == null
        ? List.of(first)
        : List.of(first, new DimensionDef(
            UUID.randomUUID(), "probe_org", "발주사", null, "o.id::text", "o.name",
            secondDimJoin, DimensionValueType.CATEGORY, CatalogStatus.ACTIVE));
    return new ValidatedSpec(WidgetTemplate.BAR_CHART, "조인 중복 검증", measure, dimensions,
        List.of(), Set.of(SEED_PROJECT_ID),
        new WidgetOptions(null, "desc", null, null, null, null, null), 20);
  }

  private void execute(SemanticQueryBuilder.BuiltQuery built) {
    jdbcClient.sql(built.sql()).params(built.params()).query().listOfRows();
  }

  private static int occurrences(String sql, String needle) {
    String haystack = sql.toLowerCase(Locale.ROOT);
    String target = needle.toLowerCase(Locale.ROOT);
    int count = 0;
    int from = 0;
    while (true) {
      int at = haystack.indexOf(target, from);
      if (at < 0) {
        return count;
      }
      count++;
      from = at + target.length();
    }
  }
}
