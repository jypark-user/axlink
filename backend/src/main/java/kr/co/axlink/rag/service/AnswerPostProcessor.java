package kr.co.axlink.rag.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.co.axlink.rag.domain.ProcessedAnswer;
import kr.co.axlink.rag.domain.RetrievalSet;
import org.springframework.stereotype.Component;

@Component
public class AnswerPostProcessor {

  private static final int SNIPPET_LIMIT = 300;
  private static final Pattern FOOTNOTE = Pattern.compile("\\[(\\d{1,2})\\]");
  private static final String NO_EVIDENCE =
      "제공된 자료에서 확인할 수 없습니다.";

  public ProcessedAnswer process(String rawText, RetrievalSet set) {
    if (rawText == null || rawText.isBlank()) {
      return new ProcessedAnswer(NO_EVIDENCE, List.of(), "no_evidence");
    }
    if (set == null || set.isEmpty()) {
      return new ProcessedAnswer(NO_EVIDENCE, List.of(), "no_evidence");
    }
    List<Integer> ordered = scanInOrder(rawText);
    Map<Integer, Integer> renumber = new LinkedHashMap<>();
    List<ProcessedAnswer.SourceRef> sources = new ArrayList<>();
    int next = 1;
    for (Integer original : ordered) {
      if (original < 1 || original > set.size() || renumber.containsKey(original)) {
        continue;
      }
      int mapped = next++;
      renumber.put(original, mapped);
      var chunk = set.chunkAt(original - 1);
      sources.add(new ProcessedAnswer.SourceRef(mapped, chunk, snippetOf(chunk.content())));
    }
    String text = rewrite(rawText, renumber);
    return new ProcessedAnswer(text, sources, "stop");
  }

  private static List<Integer> scanInOrder(String text) {
    List<Integer> result = new ArrayList<>();
    Matcher matcher = FOOTNOTE.matcher(text);
    while (matcher.find()) {
      result.add(Integer.parseInt(matcher.group(1)));
    }
    return result;
  }

  private static String rewrite(String text, Map<Integer, Integer> renumber) {
    Matcher matcher = FOOTNOTE.matcher(text);
    StringBuilder out = new StringBuilder();
    int last = 0;
    while (matcher.find()) {
      int original = Integer.parseInt(matcher.group(1));
      Integer mapped = renumber.get(original);
      out.append(text, last, matcher.start());
      if (mapped != null) {
        out.append('[').append(mapped).append(']');
      }
      last = matcher.end();
    }
    out.append(text, last, text.length());
    return out.toString();
  }

  private static String snippetOf(String content) {
    if (content == null) {
      return "";
    }
    return content.length() <= SNIPPET_LIMIT ? content : content.substring(0, SNIPPET_LIMIT);
  }
}
