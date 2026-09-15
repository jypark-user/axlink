-- 확인 요청과 조치 보고 (SWFR.WEB.004~006). 발주기관이 WBS 항목·산출물·이슈·리스크·지표를
-- 짚어 확인을 요청하고, 용역사가 조치 결과를 보고하고, 발주기관이 확인해 닫는다.
-- 요청 시점의 대상 상태를 snapshot_json 에 그대로 남긴다. 보고 때 현재 상태와 나란히 놓아
-- "그 사이 무엇이 바뀌었는가"를 사람이 아니라 시스템이 보여 준다.
-- AX Link 안에만 기록하고 원천 도구에는 아무것도 쓰지 않는다 (QUR.WEB.003).

create table review_request (
  id                    uuid         not null default gen_random_uuid(),
  project_id            uuid         not null,
  target_type           varchar(40)  not null,
  target_key            varchar(300) not null,
  target_label          varchar(500) not null,
  title                 varchar(300) not null,
  body                  text         not null default '',
  status                varchar(40)  not null default 'REQUESTED',
  requested_by_user_id  uuid         not null,
  requested_at          timestamptz  not null default now(),
  snapshot_json         jsonb        not null default '{}'::jsonb,
  report_body           text,
  reported_by_user_id   uuid,
  reported_at           timestamptz,
  report_snapshot_json  jsonb,
  confirmed_by_user_id  uuid,
  confirmed_at          timestamptz,
  rerequest_count       integer      not null default 0,
  created_at            timestamptz  not null default now(),
  updated_at            timestamptz  not null default now(),
  constraint pk_review_request primary key (id),
  constraint fk_review_request__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_review_request__requested_by foreign key (requested_by_user_id) references app_user (id) on delete restrict,
  constraint fk_review_request__reported_by foreign key (reported_by_user_id) references app_user (id) on delete set null,
  constraint fk_review_request__confirmed_by foreign key (confirmed_by_user_id) references app_user (id) on delete set null,
  constraint ck_review_request__target_type check (target_type in ('WBS_ITEM','WORK_PRODUCT','ISSUE','RISK','METRIC')),
  constraint ck_review_request__status check (status in ('REQUESTED','REPORTED','CONFIRMED')),
  constraint ck_review_request__snapshot check (jsonb_typeof(snapshot_json) = 'object'),
  constraint ck_review_request__reported check ((status = 'REQUESTED') or (reported_at is not null)),
  constraint ck_review_request__confirmed check ((status = 'CONFIRMED') = (confirmed_at is not null))
);

create index ix_review_request__project_status on review_request (project_id, status);

-- 요청·보고·확인·재요청이 오간 순서 그대로. 재요청은 같은 요청 안에서 돌기 때문에
-- 현재 상태 한 줄로는 지난 보고 내용이 사라진다. 이력이 감독 기록이다.
create table review_request_event (
  id                 uuid         not null default gen_random_uuid(),
  review_request_id  uuid         not null,
  kind               varchar(40)  not null,
  body               text,
  actor_user_id      uuid         not null,
  snapshot_json      jsonb        not null default '{}'::jsonb,
  created_at         timestamptz  not null default now(),
  constraint pk_review_request_event primary key (id),
  constraint fk_review_request_event__request foreign key (review_request_id) references review_request (id) on delete cascade,
  constraint fk_review_request_event__actor foreign key (actor_user_id) references app_user (id) on delete restrict,
  constraint ck_review_request_event__kind check (kind in ('REQUESTED','REPORTED','CONFIRMED','REREQUESTED'))
);

create index ix_review_request_event__request on review_request_event (review_request_id, created_at);
