-- 매핑 규칙 기본값을 파일럿 형식({"version":1,"rules":[]})에서 빈 객체로.
-- 현행 규칙(SWFR.CON.002)은 평면 dict 이고, 빈 객체 = "기본 판별 이름을 쓴다"다.
-- 파일럿 형식으로 남아 있던 행은 규칙을 쓴 적이 없으므로 기본값으로 정규화한다.

alter table tool_connection
  alter column mapping_rules_json set default '{}'::jsonb;

update tool_connection
   set mapping_rules_json = '{}'::jsonb
 where mapping_rules_json ? 'rules';
