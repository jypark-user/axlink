package kr.co.axlink.semantic.repository;

import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedHashSet;
import java.util.Set;
import kr.co.axlink.semantic.domain.CatalogStatus;
import kr.co.axlink.semantic.domain.DimensionDef;
import kr.co.axlink.semantic.domain.DimensionValueType;
import kr.co.axlink.semantic.domain.FilterDef;
import kr.co.axlink.semantic.domain.FilterOp;
import kr.co.axlink.semantic.domain.FilterValueType;
import kr.co.axlink.semantic.domain.MeasureDef;
import kr.co.axlink.semantic.domain.MeasureValueType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class SemanticCatalogRepository {

  private final JdbcClient jdbcClient;

  public SemanticCatalogRepository(JdbcClient jdbcClient) {
    this.jdbcClient = jdbcClient;
  }

  public java.util.List<MeasureDef> findActiveMeasures() {
    return jdbcClient.sql("""
        select id, key, label, description, base_table, join_clause, row_filter,
               value_expr, value_type, unit, allowed_dimensions, allowed_filters,
               default_dimension, target_value, status
          from semantic_measure
         where status = 'ACTIVE'
         order by key
        """).query(SemanticCatalogRepository::mapMeasure).list();
  }

  public java.util.List<DimensionDef> findActiveDimensions() {
    return jdbcClient.sql("""
        select id, key, label, description, select_expr, label_expr, requires_join,
               value_type, status
          from semantic_dimension
         where status = 'ACTIVE'
         order by key
        """).query(SemanticCatalogRepository::mapDimension).list();
  }

  public java.util.List<FilterDef> findActiveFilters() {
    return jdbcClient.sql("""
        select id, key, field, op, label, description, column_expr, value_type,
               enum_values, requires_join, status
          from semantic_filter
         where status = 'ACTIVE'
         order by key
        """).query(SemanticCatalogRepository::mapFilter).list();
  }

  private static MeasureDef mapMeasure(ResultSet rs, int row) throws SQLException {
    return new MeasureDef(
        rs.getObject("id", java.util.UUID.class),
        rs.getString("key"),
        rs.getString("label"),
        rs.getString("description"),
        rs.getString("base_table"),
        rs.getString("join_clause"),
        rs.getString("row_filter"),
        rs.getString("value_expr"),
        MeasureValueType.valueOf(rs.getString("value_type")),
        rs.getString("unit"),
        toStringSet(rs.getArray("allowed_dimensions")),
        toStringSet(rs.getArray("allowed_filters")),
        rs.getString("default_dimension"),
        rs.getBigDecimal("target_value"),
        CatalogStatus.parse(rs.getString("status")));
  }

  private static DimensionDef mapDimension(ResultSet rs, int row) throws SQLException {
    return new DimensionDef(
        rs.getObject("id", java.util.UUID.class),
        rs.getString("key"),
        rs.getString("label"),
        rs.getString("description"),
        rs.getString("select_expr"),
        rs.getString("label_expr"),
        rs.getString("requires_join"),
        DimensionValueType.valueOf(rs.getString("value_type")),
        CatalogStatus.parse(rs.getString("status")));
  }

  private static FilterDef mapFilter(ResultSet rs, int row) throws SQLException {
    return new FilterDef(
        rs.getObject("id", java.util.UUID.class),
        rs.getString("key"),
        rs.getString("field"),
        FilterOp.parse(rs.getString("op")),
        rs.getString("label"),
        rs.getString("description"),
        rs.getString("column_expr"),
        FilterValueType.valueOf(rs.getString("value_type")),
        toStringSet(rs.getArray("enum_values")),
        rs.getString("requires_join"),
        CatalogStatus.parse(rs.getString("status")));
  }

  private static Set<String> toStringSet(Array array) throws SQLException {
    Set<String> result = new LinkedHashSet<>();
    if (array == null) {
      return result;
    }
    for (Object item : (Object[]) array.getArray()) {
      if (item != null) {
        result.add(String.valueOf(item));
      }
    }
    return result;
  }
}
