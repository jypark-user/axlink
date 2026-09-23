-- 활동 기록과 알림 (2026-09-23 결정).
--
-- 발주기관과 용역사가 서로의 행동과 바뀐 것을 이벤트로 본다. 기록은 사업 단위 한 표이고,
-- 알림은 그 위에 "내 역할이 알아야 할 것" 과 사용자별 마지막 확인 시각을 얹은 것이다.
-- 항목별 읽음은 두지 않는다. 마지막 확인 시각 하나면 미읽음 수가 나온다.
--
-- audience: CLIENT(발주기관이 알아야 할 것) · CONTRACTOR(용역사) · ALL(둘 다). 최고관리자는 전부 본다.
-- actor_user_id 가 null 이면 시스템(동기화·판정)이 일으킨 일이다.

create table activity_event (
  id             uuid         primary key default gen_random_uuid(),
  project_id     uuid         not null references project(id) on delete cascade,
  occurred_at    timestamptz  not null default now(),
  kind           varchar(40)  not null,
  audience       varchar(12)  not null,
  actor_user_id  uuid         references app_user(id) on delete set null,
  actor_label    varchar(120) not null,          -- 사람 이름 또는 "동기화"·"판정"
  target_type    varchar(40),                    -- REVIEW_REQUEST · DOCUMENT · WBS_ITEM · ISSUE · SYNC_JOB
  target_key     varchar(200),                   -- 상세로 가는 열쇠(요청 id, 문서 id, WBS 번호…)
  summary        varchar(500) not null,          -- 한 줄. 화면에 그대로 보인다
  detail_json    jsonb        not null default '{}'::jsonb,
  constraint ck_activity_event__audience check (audience in ('CLIENT','CONTRACTOR','ALL'))
);

create index ix_activity_event__project_time on activity_event (project_id, occurred_at desc);
create index ix_activity_event__time on activity_event (occurred_at desc);

create table notification_seen (
  user_id   uuid         primary key references app_user(id) on delete cascade,
  seen_at   timestamptz  not null default now()
);
