package kr.co.axlink.common.web;

import java.util.List;

public record PageQuery(Integer page, Integer size, List<String> sort) {

  private static final int DEFAULT_SIZE = 20;
  private static final int MAX_SIZE = 100;

  /**
   * 한도를 벗어난 값은 막지 않고 한도로 맞춰 받는다 —
   * 이 검사는 파라미터를 담는 도중에 돌아서, 예외를 던지면 잘못된 요청이 500 으로 나갔다.
   */
  public PageQuery {
    page = page == null || page < 0 ? 0 : page;
    size = size == null ? DEFAULT_SIZE : Math.min(MAX_SIZE, Math.max(1, size));
    sort = sort == null ? List.of() : List.copyOf(sort);
  }

  public static PageQuery first() {
    return new PageQuery(0, DEFAULT_SIZE, List.of());
  }

  public int offset() {
    return page * size;
  }

  public int limit() {
    return size;
  }
}
