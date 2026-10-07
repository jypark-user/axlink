-- 원천 근거가 없는 이슈 심각도를 '미지정'(null)으로 둔다 (SWFR.PIP.002, GH-116).
--
-- 지금까지 수집 매핑이 근거 없이 MAJOR 를 넣었다.
--   GitHub: 원천에 심각도가 없는데 to_issue 가 MAJOR 고정
--   Redmine: 우선순위(보통·높음 등)를 심각도로 바꿨다. 이 대응표는 합의·설계 문서에 근거가 없다
-- 그래서 일반 이슈 전부가 '중대'로 보이고 고위험 집계에 들어갔다.
--
-- 심각도는 원천에 근거가 있을 때만 둔다. 원천 우선순위는 심각도와 따로 원문 그대로 보존한다.

alter table issue alter column severity drop not null;
alter table issue alter column severity drop default;
alter table issue add column source_priority varchar(60);   -- 원천 우선순위 원문(Redmine '보통' 등)

-- 기존 값 정정. 수집 매핑이 근거 없이 만든 값만 고친다.
-- 수기(MANUAL)·문서(DOCUMENT) 행, 원천 연결을 확인할 수 없는 행은 그대로 둔다.

-- Redmine: 원천 우선순위를 먼저 보존한다
update issue i
   set source_priority = left(ra.payload_jsonb -> 'priority' ->> 'name', 60)
  from tool_connection c, raw_artifact ra
 where c.id = i.tool_connection_id and c.tool = 'REDMINE' and i.source_kind = 'TOOL'
   and ra.tool_connection_id = i.tool_connection_id and ra.external_id = i.external_id;

-- GitHub: 원천에 심각도가 없으니 매핑이 넣을 수 있는 값은 MAJOR 하나뿐이었다
update issue i
   set severity = null
  from tool_connection c
 where c.id = i.tool_connection_id and c.tool = 'GITHUB' and i.source_kind = 'TOOL'
   and i.severity = 'MAJOR';

-- Redmine: 심각도는 우선순위에서 바꾼 값뿐이었다(근거 없는 대응표)
update issue i
   set severity = null
  from tool_connection c
 where c.id = i.tool_connection_id and c.tool = 'REDMINE' and i.source_kind = 'TOOL';

-- 시맨틱 차원·필터: 미지정을 따로 묶는다. 빈칸(null)으로 흘리면 위젯이 이름 없는 막대를 그린다
-- 표시 이름도 같이 낸다(contractor_org 의 '미지정' 과 같은 방식). AI 답변 재료가 이 이름을 읽는다
update semantic_dimension
   set select_expr = 'coalesce(e.severity, ''UNSPECIFIED'')',
       label_expr = 'case coalesce(e.severity, ''UNSPECIFIED'') when ''BLOCKER'' then ''치명'' '
                    'when ''CRITICAL'' then ''심각'' when ''MAJOR'' then ''중대'' '
                    'when ''MINOR'' then ''경미'' when ''TRIVIAL'' then ''사소'' else ''미지정'' end',
       description = '이슈 심각도별로 나눈다. 원천에 심각도가 없으면 미지정이다(낮은 위험이라는 뜻이 아니다)'
 where key = 'issue_severity';

update semantic_filter
   set column_expr = 'coalesce(e.severity, ''UNSPECIFIED'')',
       enum_values = array_append(enum_values, 'UNSPECIFIED')
 where key = 'issue_severity__in' and not ('UNSPECIFIED' = any(enum_values));
