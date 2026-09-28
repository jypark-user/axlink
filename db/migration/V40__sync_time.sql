-- 수집 설정을 스냅샷과 같은 꼴로 (SWFR.CON.005). 빈도 + 기준 시각.
--
-- 하루 한 번을 고르면 그 시각에 돈다. 더 잦은 주기는 마지막 수집 뒤 간격으로 돈다.
-- 12시간 선택지를 더해 스냅샷 빈도와 단이 맞게 한다.

alter table project_schedule
  add column sync_hour   integer not null default 6,
  add column sync_minute integer not null default 0,
  add constraint ck_project_schedule__sync_hour   check (sync_hour between 0 and 23),
  add constraint ck_project_schedule__sync_minute check (sync_minute between 0 and 59);

alter table project_schedule drop constraint ck_project_schedule__interval;
alter table project_schedule add constraint ck_project_schedule__interval
  check (sync_interval_minutes in (0, 15, 30, 60, 180, 360, 720, 1440));
