-- 알리지 않고 기록만 하는 활동 (2026-09-28).
--
-- 일별 스냅샷처럼 매일 일어나는 일은 활동 탭에는 남아야 하지만 알림으로 울리면 소음이다.
-- audience 에 LOG 를 더한다. 알림은 역할·ALL 만 보므로 LOG 는 저절로 빠진다.

alter table activity_event drop constraint ck_activity_event__audience;
alter table activity_event add constraint ck_activity_event__audience
  check (audience in ('CLIENT','CONTRACTOR','ALL','LOG'));
