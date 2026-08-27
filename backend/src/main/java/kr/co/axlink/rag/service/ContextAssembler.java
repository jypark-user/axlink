package kr.co.axlink.rag.service;

import java.util.ArrayList;
import java.util.List;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmRole;
import kr.co.axlink.ai.prompt.Prompts;
import kr.co.axlink.rag.domain.AskContext;
import kr.co.axlink.rag.domain.DocChunk;
import kr.co.axlink.rag.domain.MessageRole;
import kr.co.axlink.rag.domain.RetrievalSet;
import kr.co.axlink.rag.dto.QueryRouting;
import org.springframework.stereotype.Component;

@Component
public class ContextAssembler {

  private static final int CHUNK_CHAR_LIMIT = 1024;
  private static final String OUTPUT_FORMAT =
      """
      출력 규격
      - [근거] 청크에서 가져온 사실 문장 끝에만 청크 번호를 [n] 형태로 붙인다.
        여러 근거는 [1][3] 처럼 이어 붙인다.
      - [집계 컨텍스트]의 수치를 옮긴 문장에는 번호를 붙이지 않는다.
      - [근거] 블록에 없는 번호는 쓰지 않는다. 번호는 제시된 범위 안에서만 고른다.
      """;

  public List<LlmMessage> assemble(RetrievalSet set, String aggregateContext,
      QueryRouting routing, List<AskContext.Message> history, String question) {
    StringBuilder system = new StringBuilder(Prompts.SYNTHESIS_SYSTEM).append('\n');
    system.append(OUTPUT_FORMAT).append('\n');
    if (aggregateContext != null && !aggregateContext.isBlank()) {
      system.append("[집계 컨텍스트]\n").append(aggregateContext).append("\n\n");
    }
    system.append("[근거]\n");
    int n = 1;
    for (DocChunk chunk : set.chunks()) {
      String content = chunk.content();
      if (content.length() > CHUNK_CHAR_LIMIT) {
        content = content.substring(0, CHUNK_CHAR_LIMIT);
      }
      String location = chunk.headingPath().isEmpty()
          ? (chunk.pageNo() == null ? "" : "p." + chunk.pageNo())
          : String.join(" > ", chunk.headingPath());
      system.append('[').append(n).append("] ")
          .append(chunk.sourceTitle());
      if (!location.isEmpty()) {
        system.append(" · ").append(location);
      }
      system.append('\n').append(content).append("\n\n");
      n++;
    }
    List<LlmMessage> messages = new ArrayList<>();
    messages.add(LlmMessage.system(system.toString()));
    if (history != null) {
      int from = Math.max(0, history.size() - 3);
      for (int i = from; i < history.size(); i++) {
        AskContext.Message m = history.get(i);
        messages.add(new LlmMessage(
            m.role() == MessageRole.USER ? LlmRole.USER : LlmRole.ASSISTANT,
            m.content()));
      }
    }
    messages.add(LlmMessage.user(question));
    return messages;
  }
}
