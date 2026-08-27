package kr.co.axlink.dashboard.dto;

public record GridItem(
    String i,
    int x,
    int y,
    int w,
    int h,
    Integer minW,
    Integer minH) {
}
