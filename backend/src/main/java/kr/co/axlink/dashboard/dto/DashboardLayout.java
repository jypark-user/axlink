package kr.co.axlink.dashboard.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

/** layout_json 컬럼 기본값에 있는 legacy "version" 키처럼, 저장된 JSON 이 모르는 키를 가져도 읽는다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record DashboardLayout(
    List<GridItem> lg,
    List<GridItem> md,
    List<GridItem> sm) {

  public static DashboardLayout empty() {
    return new DashboardLayout(List.of(), List.of(), List.of());
  }
}
