-- 사업별 수집 주기와 스냅샷 시각 (SWFR.PIP.005 · SWFR.CON.005).
--
-- 일별 스냅샷과 증분 수집은 스스로 돌아야 한다. cron 에 맡기면 폐쇄망 반입 요소가 하나 늘고
-- 개발·시연·납품 환경이 달라진다. 서버 안 스케줄러가 이 표를 읽어 돈다.
--
-- 수집 주기는 선택지 중 하나다. 너무 짧으면 원천 도구의 호출 한도를 먹으니 15분이 최소이고,
-- 0 은 "자동 수집 안 함(수동만)" 이다. 스냅샷 시각은 사업 시간대(Asia/Seoul) 기준 시·분이다.

create table project_schedule (
  project_id             uuid        primary key references project(id) on delete cascade,
  sync_interval_minutes  integer     not null default 30,
  snapshot_hour          integer     not null default 0,
  snapshot_minute        integer     not null default 10,
  updated_by_user_id     uuid        references app_user(id) on delete set null,
  updated_at             timestamptz not null default now(),
  constraint ck_project_schedule__interval
    check (sync_interval_minutes in (0, 15, 30, 60, 180, 360, 1440)),
  constraint ck_project_schedule__hour   check (snapshot_hour between 0 and 23),
  constraint ck_project_schedule__minute check (snapshot_minute between 0 and 59)
);
