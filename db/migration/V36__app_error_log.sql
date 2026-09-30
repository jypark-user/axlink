-- 서버 오류 기록. 최고관리자가 화면에서 본다.
--
-- 폐쇄망에서는 서버 로그 파일을 열어 볼 사람이 없다. 500 으로 끝난 요청은 경로·메시지·
-- 스택을 표에 남겨 관리자 화면에서 바로 보게 한다. 기록 자체가 실패해도 응답은 나간다.

create table app_error_log (
  id           uuid         primary key default gen_random_uuid(),
  occurred_at  timestamptz  not null default now(),
  method       varchar(10)  not null,
  path         text         not null,
  status_code  integer      not null,
  code         varchar(40)  not null,
  message      text         not null,
  exception    varchar(200),
  traceback    text,
  user_id      uuid         references app_user(id) on delete set null
);

create index ix_app_error_log__occurred on app_error_log (occurred_at desc);
