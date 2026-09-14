-- 추적관계마다 근거를 남긴다 (SWFR.PIP.004).
-- 자동 생성 링크는 근거 없이 존재할 수 없다 (QUR.PIP.001). 수기 링크는 사람이 근거다.

alter table trace_link
  add column evidence_kind varchar(40),
  add column evidence_text text,
  add column evidence_url  text;

alter table trace_link
  add constraint ck_trace_link__evidence_kind check (evidence_kind is null or evidence_kind in (
    'TEXT_REQ_CODE',    -- 커밋·PR·이슈 본문에 적힌 요구사항 코드
    'TEXT_ISSUE_REF',   -- 커밋·PR 본문의 GH-n / RM-n 참조
    'TEXT_FILE_PATH',   -- 커밋·PR·이슈 본문에 적힌 산출물 파일 경로
    'CUSTOM_FIELD',     -- Redmine 커스텀 필드 REQ ID
    'ISSUE_RELATION')); -- Redmine issue relations

alter table trace_link
  add constraint ck_trace_link__auto_evidence check (origin <> 'AUTO' or evidence_kind is not null);
