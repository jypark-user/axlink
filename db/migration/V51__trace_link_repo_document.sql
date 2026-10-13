-- 저장소 설계 문서를 설계 근거로 잇고, 분류 정정과 끊김을 구분한다 (ARC-024, GH-132).
--
-- 출발점 REPO_DOCUMENT 는 수집한 원본(raw_artifact) 의 id 다. 정식 산출물(WORK_PRODUCT)과 다르다.
-- 근거 DOC_REQ_REF 는 문서의 명시적 참조(관련 행·대응표·절 제목)다. 위치는 evidence_meta 에 둔다.
-- SUPERSEDED 는 분류 규칙이 바뀌어 다른 링크로 대체됐거나 제외된 것, BROKEN 은 원천 근거가 사라진 것이다.

alter table trace_link drop constraint ck_trace_link__from_type;
alter table trace_link add constraint ck_trace_link__from_type check (from_type in (
  'REQUIREMENT','ISSUE','WORK_PRODUCT','RISK','CODE_CHANGE','CHANGE_REQUEST','CORRECTION_ACTION',
  'REPO_DOCUMENT'));

alter table trace_link drop constraint ck_trace_link__status;
alter table trace_link add constraint ck_trace_link__status check (status in (
  'ACTIVE','BROKEN','SUPERSEDED'));

alter table trace_link drop constraint ck_trace_link__evidence_kind;
alter table trace_link add constraint ck_trace_link__evidence_kind check (evidence_kind is null or evidence_kind in (
  'TEXT_REQ_CODE', 'TEXT_ISSUE_REF', 'TEXT_FILE_PATH', 'CUSTOM_FIELD', 'ISSUE_RELATION',
  'DOC_REQ_REF'));   -- 저장소 설계 문서의 명시적 요구사항 참조

alter table trace_link
  add column evidence_meta     jsonb,        -- 경로·커밋·blob·줄·절·문서 상태 등 근거 위치
  add column status_reason     text,         -- 대체·제외·끊김의 사유
  add column status_changed_at timestamptz,  -- 상태가 마지막으로 바뀐 시각
  add column superseded_by     uuid;         -- 이 링크를 대체한 링크

alter table trace_link
  add constraint fk_trace_link__superseded_by foreign key (superseded_by)
    references trace_link (id) on delete set null;
