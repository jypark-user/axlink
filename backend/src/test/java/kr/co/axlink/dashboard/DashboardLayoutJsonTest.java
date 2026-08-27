package kr.co.axlink.dashboard;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import kr.co.axlink.common.json.JsonCodec;
import kr.co.axlink.dashboard.dto.DashboardLayout;
import org.junit.jupiter.api.Test;

/** layout_json 컬럼 기본값(`version` 포함)을 읽지 못하면 위젯을 하나도 못 붙인다. */
class DashboardLayoutJsonTest {

  private final JsonCodec codec = new JsonCodec(new ObjectMapper());

  @Test
  void readsColumnDefaultWithLegacyVersionKey() {
    DashboardLayout layout =
        codec.read("{\"version\":1,\"lg\":[],\"md\":[],\"sm\":[]}", DashboardLayout.class);

    assertThat(layout.lg()).isEmpty();
    assertThat(layout.md()).isEmpty();
    assertThat(layout.sm()).isEmpty();
  }
}
