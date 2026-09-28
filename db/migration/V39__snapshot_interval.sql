-- 스냅샷 갱신 빈도 (SWFR.PIP.005).
--
-- 과업지시서 Ⅱ.2 의 "일별" 은 최소 보장이다. 그보다 자주 찍고 싶은 사업은 12·6·3·1시간마다
-- 그날 줄을 최신 값으로 다시 찍는다. 하루 한 줄 구조는 그대로라 추이는 일 단위이고, 그날
-- 값이 더 신선해질 뿐이다. 24 가 기본(정한 시각에 하루 한 번)이다.

alter table project_schedule
  add column snapshot_interval_hours integer not null default 24,
  add constraint ck_project_schedule__snapshot_interval
    check (snapshot_interval_hours in (1, 3, 6, 12, 24));
