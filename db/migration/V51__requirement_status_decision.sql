-- 요구사항 상태를 근거 상태와 발주기관 지정 상태로 나눈다 (SWFR.PIP.008, ARC-025).
--
-- status 는 화면·지표·질의가 읽는 "지금 상태" 다. 지정이 있으면 지정 상태, 없으면 근거 상태다.
-- 근거 상태(evidence_status)는 수집이 원천에서 정한다. 수집은 근거 상태만 바꾸고 지정은 건드리지 않는다.
-- 지정은 발주기관이 사유와 함께 남긴다. 지정을 거두면 근거 상태로 돌아간다.

alter table requirement
  add column evidence_status    varchar(40),
  add column decided_status     varchar(40),
  add column decided_reason     text,
  add column decided_by_user_id uuid,
  add column decided_at         timestamptz;

update requirement set evidence_status = status;

alter table requirement
  add constraint ck_requirement__evidence_status check (
    evidence_status is null
    or evidence_status in ('DEFINED','DESIGNED','IMPLEMENTED','VERIFIED','ACCEPTED','REJECTED')),
  add constraint ck_requirement__decided_status check (
    decided_status is null
    or decided_status in ('DEFINED','DESIGNED','IMPLEMENTED','VERIFIED','ACCEPTED','REJECTED')),
  -- 지정에는 사유와 시각이 반드시 붙고, 지정이 없으면 셋 다 비어 있다
  add constraint ck_requirement__decision_complete check (
    (decided_status is null and decided_reason is null and decided_at is null)
    or (decided_status is not null and length(btrim(decided_reason)) > 0 and decided_at is not null)),
  -- 지정이 있으면 지금 상태는 지정 상태와 같다
  add constraint ck_requirement__decided_effective check (
    decided_status is null or status = decided_status),
  add constraint fk_requirement__decided_by foreign key (decided_by_user_id)
    references app_user (id) on delete set null;

-- 이행률 산출 근거 문장. "시험 결과서를 올리면 검증완료로 바뀐다" 는 아직 없는 동작이라 고친다.
update semantic_measure set basis =
  '검증완료(VERIFIED) 또는 인수완료(ACCEPTED) 상태인 요구사항 수를 전체 요구사항 수로 나눈 값이다. '
  '원천 이슈를 닫으면 구현완료(IMPLEMENTED)까지만 간다. 검증·인수는 발주기관이 근거를 보고 '
  '요구사항 화면에서 사유와 함께 지정한다. 올리려면: 요구사항별 시험·검토 근거를 갖춘 뒤 '
  '발주기관이 검증 또는 인수로 지정한다. 지정은 언제든 근거 상태로 되돌릴 수 있다.'
where key = 'requirement_fulfillment_rate';
