package kr.co.axlink.rag.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import kr.co.axlink.rag.domain.ChunkDraft;
import kr.co.axlink.rag.domain.DocSourceType;
import org.junit.jupiter.api.Test;

class ChunkingServiceTest {

  private final ChunkingService service = new ChunkingService();

  /** 문서에서 뽑은 글은 마침표 없이 길게 이어지는 일이 흔하다 — 그래도 조각 합계가 원문을 넘겨선 안 된다. */
  @Test
  void 문장_부호가_없어도_조각이_불어나지_않는다() {
    String body = ("요구사항고유번호 COR-%03d 요구사항 명칭 표준 준수 요구사항 분류 제약사항 "
        + "세부 내용 기술적용계획표의 기술표준이 본 사업에 부합하는지 검토하여야 하며 "
        + "변경이 필요할 경우 타당한 사유를 제시하여 발주자와 상호 협의하여 조정하여야 함 산출정보 결과표 ")
        .repeat(1);
    StringBuilder text = new StringBuilder();
    for (int i = 0; i < 200; i++) {
      text.append(String.format(body, i));
    }

    List<ChunkDraft> chunks = service.chunk(DocSourceType.DOCUMENT_UPLOAD, "제안요청서",
        text.toString(), Map.of());

    int packed = chunks.stream().mapToInt(c -> c.content().length()).sum();
    assertThat(chunks).isNotEmpty();
    assertThat(packed).isLessThan((int) (text.length() * 1.5));
  }

  @Test
  void 조각_하나가_한도를_넘지_않는다() {
    String text = "가".repeat(50_000);

    List<ChunkDraft> chunks = service.chunk(DocSourceType.DOCUMENT_UPLOAD, null, text, Map.of());

    assertThat(chunks).allSatisfy(c -> assertThat(c.content().length()).isLessThan(3_000));
  }
}
