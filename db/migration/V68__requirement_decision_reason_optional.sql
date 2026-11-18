-- 요구사항 상태 지정의 사유를 선택으로 바꾼다 (2026-11-17 사용자 결정, ARC-025 개정).
--
-- V51 은 지정이 있으면 사유(공백 아님)를 필수로 했다. 근거는 우리 설계(ARC-025)뿐이고 과업지시서·
-- 요구사항정의서에는 사유 요구가 없다. 지정은 발주기관이 직접 하는 일이라 매번 사유를 받는 부담이
-- 크다고 보고 선택으로 바꾼다. 누가·언제 지정했는지와 근거 상태는 그대로 남는다.
--
-- 지정이 있으면 시각은 여전히 있어야 하고, 지정이 없으면 셋 다 비어 있어야 한다. 사유는 있으면
-- 공백이 아니어야 한다(빈 글자는 null 로 저장한다). 이미 남은 사유는 고치지 않는다.

alter table requirement drop constraint ck_requirement__decision_complete;
alter table requirement add constraint ck_requirement__decision_complete check (
  (decided_status is null and decided_reason is null and decided_at is null)
  or (decided_status is not null and decided_at is not null
      and (decided_reason is null or length(btrim(decided_reason)) > 0)));

comment on column requirement.decided_reason is
  '발주기관이 상태를 지정한 사유. 선택(2026-11-17 전에는 필수였다). 지정이 없으면 null';
