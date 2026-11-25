-- 답변 방식 (ARC-034). 플랫폼 전체에 한 줄이다. 행이 없으면 지표 기반(STRUCTURED)이다.
-- STRUCTURED = 지표 기반: 모델이 질문을 지표·문서·목록 하나로 판정하고 서버가 그것만 집계한다.
-- AI_JUDGE   = AI 판단: 서버가 사업 자원을 모아 넘기고 모델이 그 안에서 골라 판단한다.
create table answer_setting (
  id                 smallint     not null default 1,
  mode               varchar(20)  not null default 'STRUCTURED',
  updated_by_user_id uuid,
  updated_at         timestamptz  not null default now(),
  constraint pk_answer_setting primary key (id),
  constraint ck_answer_setting__single check (id = 1),
  constraint ck_answer_setting__mode check (mode in ('STRUCTURED', 'AI_JUDGE')),
  constraint fk_answer_setting__updated_by foreign key (updated_by_user_id) references app_user (id) on delete set null
);

-- AI 판단으로 만든 답은 경로 종류를 따로 남긴다
alter table message drop constraint ck_message__route_type;
alter table message add constraint ck_message__route_type
  check (route_type is null or route_type in
    ('DOCUMENT','AGGREGATE','MIXED','OVERVIEW','INTENT','CLARIFY','AI_JUDGE'));
