package kr.co.axlink.rag.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.co.axlink.rag.domain.ChunkDraft;
import kr.co.axlink.rag.domain.DocSourceType;
import org.springframework.stereotype.Component;

@Component
public class ChunkingService {

  private static final double CHARS_PER_TOKEN = 2.4;
  private static final int TARGET_TOKENS = 800;
  private static final int MIN_TOKENS = 200;
  private static final int MAX_TOKENS = 1000;
  private static final double OVERLAP_RATIO = 0.15;

  private static final Set<DocSourceType> SINGLE_CHUNK = Set.of(
      DocSourceType.REQUIREMENT, DocSourceType.ISSUE, DocSourceType.RISK,
      DocSourceType.CHANGE_REQUEST, DocSourceType.CORRECTION_ACTION,
      DocSourceType.PROGRESS_RECORD);

  private static final Pattern HEADING = Pattern.compile(
      "^#{1,6}\\s|^제\\s*\\d+\\s*[장절]|^\\d+(\\.\\d+)*\\s",
      Pattern.MULTILINE);

  public List<ChunkDraft> chunk(DocSourceType type, String title, String body,
      Map<String, Object> meta) {
    String full = (title == null ? "" : title + "\n\n") + (body == null ? "" : body);
    if (full.isBlank()) {
      return List.of();
    }
    Integer pageNo = meta == null ? null : (Integer) meta.get("pageNo");
    if (SINGLE_CHUNK.contains(type) && tokensOf(full) <= MAX_TOKENS) {
      return List.of(draft(full, List.of(), pageNo, meta));
    }
    List<Section> sections = splitByHeading(full);
    List<ChunkDraft> result = new ArrayList<>();
    String tail = null;
    for (Section section : sections) {
      List<String> sentences = splitSentences(section.body);
      tail = pack(sentences, section.headingPath, pageNo, meta, tail, result);
    }
    if (result.isEmpty()) {
      result.add(draft(full, List.of(), pageNo, meta));
    }
    return result;
  }

  private String pack(List<String> sentences, List<String> headingPath, Integer pageNo,
      Map<String, Object> meta, String tail, List<ChunkDraft> out) {
    StringBuilder current = new StringBuilder();
    int currentTokens = 0;
    int overlapTokens = (int) Math.round(TARGET_TOKENS * OVERLAP_RATIO);
    if (tail != null) {
      current.append(tail).append(' ');
      currentTokens += tokensOf(tail);
    }
    for (String sentence : sentences) {
      int sTokens = tokensOf(sentence);
      if (currentTokens + sTokens > MAX_TOKENS && currentTokens >= MIN_TOKENS) {
        out.add(draft(current.toString().strip(), headingPath, pageNo, meta));
        String tailText = tailOverlap(current.toString(), overlapTokens);
        current = new StringBuilder(tailText == null ? "" : tailText + " ");
        currentTokens = tailText == null ? 0 : tokensOf(tailText);
      }
      current.append(sentence).append(' ');
      currentTokens += sTokens;
    }
    if (currentTokens >= MIN_TOKENS) {
      out.add(draft(current.toString().strip(), headingPath, pageNo, meta));
      return tailOverlap(current.toString(), overlapTokens);
    }
    if (currentTokens > 0) {
      out.add(draft(current.toString().strip(), headingPath, pageNo, meta));
    }
    return null;
  }

  private String tailOverlap(String text, int overlapTokens) {
    List<String> sentences = splitSentences(text);
    StringBuilder tail = new StringBuilder();
    int tokens = 0;
    for (int i = sentences.size() - 1; i >= 0; i--) {
      int t = tokensOf(sentences.get(i));
      if (tokens + t > overlapTokens && tail.length() > 0) {
        break;
      }
      tail.insert(0, sentences.get(i) + " ");
      tokens += t;
    }
    if (tail.length() == 0) {
      return null;
    }
    // 문장 하나가 겹침 한도보다 길 수 있다. 통째로 물고 가면 다음 조각이 앞 조각을 되풀이한다.
    String text2 = tail.toString().strip();
    int maxChars = (int) Math.round(overlapTokens * CHARS_PER_TOKEN);
    return text2.length() <= maxChars ? text2 : text2.substring(text2.length() - maxChars).strip();
  }

  private List<Section> splitByHeading(String text) {
    List<Section> sections = new ArrayList<>();
    Matcher matcher = HEADING.matcher(text);
    int last = 0;
    List<String> path = new ArrayList<>();
    while (matcher.find()) {
      if (matcher.start() > last) {
        addSection(sections, path, text.substring(last, matcher.start()));
      }
      String headingLine = text.substring(matcher.start(), text.indexOf('\n', matcher.start()));
      if (path.size() < 6) {
        path = new ArrayList<>(path);
        path.add(headingLine.strip());
      }
      last = matcher.start();
    }
    if (last < text.length()) {
      addSection(sections, path, text.substring(last));
    }
    if (sections.isEmpty()) {
      sections.add(new Section(List.of(), text));
    }
    return sections;
  }

  private void addSection(List<Section> sections, List<String> path, String body) {
    if (!body.isBlank()) {
      sections.add(new Section(List.copyOf(path), body.strip()));
    }
  }

  private static List<String> splitSentences(String text) {
    String[] byNewline = text.split("\\n\\s*\\n");
    List<String> sentences = new ArrayList<>();
    for (String block : byNewline) {
      String[] parts = block.split("(?<=[.!?。])\\s+");
      for (String part : parts) {
        if (!part.isBlank()) {
          split(part.strip(), sentences);
        }
      }
    }
    return sentences;
  }

  /**
   * 문장 부호 없이 길게 이어지는 글 — 표에서 뽑은 줄이 흔히 그렇다 — 은 조각 한도에 맞춰 끊는다.
   * 끊지 않으면 문장 하나가 조각보다 커져 겹침이 조각 전체를 삼킨다.
   */
  private static void split(String sentence, List<String> out) {
    int limit = (int) Math.round(MAX_TOKENS * CHARS_PER_TOKEN);
    while (sentence.length() > limit) {
      int cut = sentence.lastIndexOf(' ', limit);
      if (cut <= 0) {
        cut = limit;
      }
      out.add(sentence.substring(0, cut).strip());
      sentence = sentence.substring(cut).strip();
    }
    if (!sentence.isBlank()) {
      out.add(sentence);
    }
  }

  private ChunkDraft draft(String content, List<String> headingPath, Integer pageNo,
      Map<String, Object> meta) {
    Map<String, Object> chunkMeta = new LinkedHashMap<>();
    if (meta != null) {
      chunkMeta.putAll(meta);
    }
    if (!headingPath.isEmpty()) {
      chunkMeta.put("headingPath", headingPath);
    }
    if (pageNo != null) {
      chunkMeta.put("pageNo", pageNo);
    }
    return new ChunkDraft(content, tokensOf(content), List.copyOf(headingPath), pageNo,
        sha256(content), chunkMeta);
  }

  private static int tokensOf(String text) {
    return (int) Math.ceil(text.length() / CHARS_PER_TOKEN);
  }

  private static String sha256(String text) {
    try {
      byte[] digest = MessageDigest.getInstance("SHA-256")
          .digest(text.getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest);
    } catch (Exception e) {
      throw new IllegalStateException("SHA-256 is required", e);
    }
  }

  private record Section(List<String> headingPath, String body) {}
}
