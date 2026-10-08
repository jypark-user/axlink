-- 문서 처리 대기열 (GH-121). 업로드 접수와 추출·색인·초안을 나눈다.
-- 접수는 파일을 저장하고 행을 남기는 데서 끝나고, 나머지는 API 안의 작업자가 뒤에서 한다.
-- status 는 문서의 단계(올림·추출·구조화·확정)이고, processing_state 는 그 처리 작업의 상태다.
--   QUEUED   접수됨. 작업자가 가져가기를 기다린다
--   RUNNING  처리 중. heartbeat 가 오래 멈추면 재시작으로 끊긴 것으로 보고 다시 대기열에 넣는다
--   DONE     완료
--   FAILED   실패. 사유는 processing_error. 같은 파일을 다시 올리면 다시 처리한다

alter table document_upload add column processing_state varchar(20) not null default 'DONE';
alter table document_upload add column processing_error text;
alter table document_upload add column processing_attempts integer not null default 0;
alter table document_upload add column processing_started_at timestamptz;
alter table document_upload add column processing_heartbeat_at timestamptz;
alter table document_upload add column processed_at timestamptz;
-- 단계별 걸린 시간(초). 느린 문서가 어디서 오래 걸리는지 남긴다
alter table document_upload add column processing_steps jsonb;

alter table document_upload add constraint ck_document_upload__processing_state
  check (processing_state in ('QUEUED','RUNNING','DONE','FAILED'));

-- 지금까지 올린 문서는 요청 안에서 처리가 끝났다. 실패했던 것만 실패로 둔다
update document_upload
   set processing_state = case when status = 'FAILED' then 'FAILED' else 'DONE' end,
       processing_error = case when status = 'FAILED' then error end;

create index ix_document_upload__processing on document_upload (processing_state, created_at)
  where processing_state in ('QUEUED','RUNNING');
