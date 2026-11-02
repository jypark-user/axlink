-- 같은 대상 식별자라도 서버가 다르면 다른 연결이다 (GH-145, ARC-027 5절)
--
-- V1 의 uq_tool_connection__target(project_id, tool, target_resource) 에는 서버 주소가 없었다.
-- 그래서 Redmine 서버 두 곳의 프로젝트 식별자가 같으면(둘 다 pms) 둘째 연결을 등록할 수 없었다.
-- 원본·이슈 키는 이미 연결 단위라 데이터 구분은 따로 손댈 것이 없다.
--
-- 주소는 대소문자와 끝 빗금을 무시하고 비교한다. https://rm.example/ 과 https://RM.example 은 같은 서버다.
-- 새 제약은 예전 제약보다 느슨하므로 기존 행이 걸리는 일은 없다.
alter table tool_connection drop constraint uq_tool_connection__target;

create unique index uq_tool_connection__target
    on tool_connection (project_id, tool, rtrim(lower(base_url), '/'), target_resource);
