package kr.co.axlink.semantic.domain;

import java.util.List;

public record BoundFilter(
    FilterDef def,
    List<Object> values) {
}
