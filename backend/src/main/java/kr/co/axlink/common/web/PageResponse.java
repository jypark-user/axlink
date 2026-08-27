package kr.co.axlink.common.web;

import java.util.List;

public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean hasNext) {

  public static <T> PageResponse<T> of(List<T> content, PageQuery q, long total) {
    int totalPages = q.size() == 0 ? 0 : (int) ((total + q.size() - 1) / q.size());
    return new PageResponse<>(
        content == null ? List.of() : content,
        q.page(),
        q.size(),
        total,
        totalPages,
        (long) (q.page() + 1) * q.size() < total);
  }
}
