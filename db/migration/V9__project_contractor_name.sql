-- 사업 기본 정보의 용역사. 계정이 아직 없는 용역사도 이름으로 적어 둘 수 있어야 한다.
-- project_assignment(FK)는 계정이 생긴 뒤의 실제 접근 권한이고, 이 칼럼은 기본 정보 표기다.
alter table project add column contractor_name varchar(200);
