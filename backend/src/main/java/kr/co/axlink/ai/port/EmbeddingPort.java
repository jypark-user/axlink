package kr.co.axlink.ai.port;

import java.util.List;

public interface EmbeddingPort {

  List<float[]> embed(List<String> texts);

  int dimension();
}
