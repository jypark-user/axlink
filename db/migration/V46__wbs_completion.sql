-- WBS 작업 완료 확인 (ARC-019). 보고 진척률 옆에 '완료 확인율'을 둔다.
--
-- 보고 진척률은 용역사가 WBS 파일에 적은 실적이다. 완료 확인율은 발주기관이 '작업 완료 확인'
-- 요청으로 완료를 인정한 작업의 가중치 비율이다. 일반 확인 요청은 들지 않는다.
--
-- 작업 식별과 범위는 따로 본다.
--   task_key  : 작업의 정체. 계획서를 다시 올려도 같은 작업임이 확인될 때만 이어 간다
--   scope_hash: 작업이 무엇을 하는가(작업명 + 산출물 열). 바뀌면 이전 확인으로 셀 수 없다
-- 정체를 이을지는 적재 코드가 정한다(wbs_repository.replace_plan). 확인할 수 없으면 새 키다.

alter table wbs_item add column task_key uuid not null default gen_random_uuid();
alter table wbs_item add column key_reason varchar(20) not null default 'INITIAL';
alter table wbs_item add constraint ck_wbs_item__key_reason
  check (key_reason in ('INITIAL','NEW','CONTINUED','RENAMED','REAPPEARED','RESTRUCTURED','LEAF_CHANGED'));
-- 비교용 정규화. 공백을 하나로 모으고 대소문자를 무시한다. 함수가 모두 불변이라 생성 열로 둔다
alter table wbs_item add column name_key text generated always as
  (lower(regexp_replace(btrim(name), '\s+', ' ', 'g'))) stored;
alter table wbs_item add column scope_hash text generated always as
  (md5(lower(regexp_replace(btrim(name), '\s+', ' ', 'g')) || chr(31) ||
       lower(regexp_replace(btrim(coalesce(deliverable, '')), '\s+', ' ', 'g')))) stored;
create unique index uq_wbs_item__task_key on wbs_item (task_key);

-- 확인 요청의 목적. 기존 요청은 모두 일반이다(소급하지 않는다)
alter table review_request add column purpose varchar(20) not null default 'GENERAL';
alter table review_request add column completion_scope text;   -- 확인할 완료 내용
alter table review_request add column task_key uuid;           -- 요청한 그 작업
alter table review_request add constraint ck_review_request__purpose
  check (purpose in ('GENERAL','WBS_COMPLETION'));
alter table review_request add constraint ck_review_request__completion
  check (purpose = 'GENERAL' or
         (target_type = 'WBS_ITEM' and task_key is not null
          and completion_scope is not null and btrim(completion_scope) <> ''));

-- 한 작업에 열린 완료 확인 요청은 하나뿐이다. 같은 요청이 두 번 들어가면 확인도 두 번 된다
create unique index uq_review_request__open_completion on review_request (task_key)
  where purpose = 'WBS_COMPLETION' and status in ('REQUESTED','REPORTED');

-- 조치 보고에 붙인 근거. 파일이 없는 작업도 시험·시연·회의 기록을 근거로 적는다
alter table review_request_event add column evidence_json jsonb;
-- 완료 확인 철회는 요청 상태를 되돌리지 않고 이력 한 줄로 남긴다
alter table review_request_event drop constraint ck_review_request_event__kind;
alter table review_request_event add constraint ck_review_request_event__kind
  check (kind in ('REQUESTED','REPORTED','CONFIRMED','REREQUESTED','COMPLETION_WITHDRAWN'));

-- 완료 확인 기록. 추가만 한다. 철회도 한 줄을 더한다. 개정이 와도 지난 줄은 남는다
create table wbs_completion_record (
  id                  uuid         primary key default gen_random_uuid(),
  project_id          uuid         not null references project(id) on delete cascade,
  task_key            uuid         not null,
  wbs_id              varchar(40)  not null,      -- 그때의 번호. 정체가 아니라 표시용
  review_request_id   uuid         not null references review_request(id) on delete restrict,
  kind                varchar(20)  not null,
  decided_by_user_id  uuid         not null references app_user(id) on delete restrict,
  decided_at          timestamptz  not null default now(),
  scope_hash          text         not null,
  weight_at           numeric(9,6) not null,      -- 확인 당시 가중치
  plan_work_product_id uuid,                      -- 확인 당시 WBS 계획서 버전
  plan_version        varchar(40),
  reported_actual     numeric(7,4),               -- 확인 당시 보고 실적. 덮어쓰지 않는다
  completion_scope    text         not null,
  item_json           jsonb        not null,      -- 작업명·산출물 열·기간
  evidence_json       jsonb        not null,      -- 파일 대조·정식 제출·승인·용역사 근거
  note                text,
  constraint ck_wbs_completion_record__kind check (kind in ('CONFIRMED','WITHDRAWN')),
  -- 같은 요청으로 확인·철회가 두 번 들어가지 않는다(중복 클릭·재시도)
  constraint uq_wbs_completion_record__request_kind unique (review_request_id, kind)
);

create index ix_wbs_completion_record__task on wbs_completion_record (task_key, decided_at desc);
create index ix_wbs_completion_record__project on wbs_completion_record (project_id);

-- 지금 WBS 말단 작업마다 완료 확인 상태. 화면·시맨틱 지표가 같은 뷰를 읽는다(절대 규칙 1)
--   CONFIRMED  : 마지막 기록이 확인이고 범위가 그대로
--   RECONFIRM  : 마지막 기록이 확인인데 범위(작업명·산출물 열)가 바뀜
--   WITHDRAWN  : 마지막 기록이 철회
--   NONE       : 이 작업에 기록이 없음
create view v_wbs_completion as
select w.project_id, w.id as wbs_item_id, w.task_key, w.wbs_id, w.name, w.deliverable,
       w.weight, w.actual, w.end_on, w.key_reason, w.scope_hash,
       r.id as record_id, r.kind as last_kind, r.decided_at, r.weight_at, r.plan_version,
       r.reported_actual as actual_at, r.review_request_id,
       case
         when r.id is null then 'NONE'
         when r.kind = 'WITHDRAWN' then 'WITHDRAWN'
         when r.scope_hash <> w.scope_hash then 'RECONFIRM'
         else 'CONFIRMED'
       end as completion_status,
       -- 같은 번호에 예전 작업의 확인이 있었는데 정체를 잇지 못한 경우. 승계하지 않고 알린다
       exists (
         select 1 from wbs_completion_record p
          where p.project_id = w.project_id and p.wbs_id = w.wbs_id
            and p.task_key <> w.task_key and p.kind = 'CONFIRMED'
       ) as predecessor_confirmed
  from wbs_item w
  left join lateral (
    select * from wbs_completion_record c
     where c.task_key = w.task_key
     order by c.decided_at desc, c.id desc
     limit 1
  ) r on true
 where w.active and w.weight is not null;

alter table semantic_measure drop constraint ck_semantic_measure__base_table;
alter table semantic_measure add constraint ck_semantic_measure__base_table check (base_table in (
  'requirement','issue','work_product','risk','code_change','change_request','correction_action',
  'progress_record','progress_snapshot','wbs_item','v_wbs_completion'));

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status, basis) values
('wbs_completion_rate', '완료 확인율',
 'WBS 말단 작업 가중치 중 발주기관이 작업 완료 확인 요청으로 완료를 인정한 작업의 가중치 비율(%). '
 '보고 진척률과 다르다. "완료 확인된 작업은 얼마나 되나" 질문에 사용',
 'v_wbs_completion', null, null,
 'round(100.0 * sum(e.weight) filter (where e.completion_status = ''CONFIRMED'') '
 '/ nullif(sum(e.weight), 0), 2)',
 'RATE_PCT', '%',
 '{project}',
 '{project_id__in}',
 null, 'ACTIVE',
 '완료 확인 기록 기준이다. 현재 WBS 말단 작업의 가중치 합을 분모로, 그중 발주기관이 '
 '''작업 완료 확인'' 요청으로 완료를 인정했고 그 뒤 작업명·산출물 열이 바뀌지 않은 작업의 '
 '가중치 합을 분자로 한다. 일반 확인 요청, 산출물 승인, 시험 통과만으로는 들지 않는다. '
 '가중치는 현재 WBS 기준이다. 말단 작업이 없으면 산출할 수 없다.');
