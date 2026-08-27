-- 용역사 할당의 세부 권한 3종을 없앤다.
-- 할당 자체가 권한이다 — 할당된 프로젝트의 도구 연동은 용역사의 일이고,
-- 문서 업로드·대시보드 열람은 역할 단계에서 이미 닫혀 있어 토글이 아무 일도 하지 않았다.
alter table project_assignment drop column permissions_json;
