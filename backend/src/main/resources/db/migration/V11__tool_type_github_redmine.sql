-- 2026-08-21 범위 확정: 형상관리 GITHUB · 프로젝트 관리 REDMINE 2종만 남긴다.
-- JIRA/GITLAB/NOTION 연결이 남아 있으면 이 마이그레이션은 실패한다. 의도한 동작이다 —
-- 그 연결을 어떻게 처리할지는 운영자가 정할 일이지 마이그레이션이 조용히 지울 일이 아니다.
alter table tool_connection drop constraint ck_tool_connection__tool;
alter table tool_connection add constraint ck_tool_connection__tool
  check (tool in ('GITHUB','REDMINE'));
