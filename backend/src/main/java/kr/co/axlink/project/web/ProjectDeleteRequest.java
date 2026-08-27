package kr.co.axlink.project.web;

import jakarta.validation.constraints.NotBlank;

/** 사업 삭제 요청. 등록할 때 정한 비밀번호를 그대로 보낸다 — 서버는 해시와 맞춰 보고 버린다. */
public record ProjectDeleteRequest(@NotBlank String password) {
}
