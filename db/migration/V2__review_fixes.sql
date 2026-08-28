alter table semantic_filter add column if not exists requires_join text;

update semantic_filter
   set requires_join = 'left join tool_connection tc on tc.id = e.tool_connection_id',
       updated_at = now()
 where key = 'contractor_org_id__in'
   and requires_join is distinct from 'left join tool_connection tc on tc.id = e.tool_connection_id';

insert into semantic_dimension (key, label, description, select_expr, label_expr, requires_join, value_type)
select 'author', '작성자',
       '형상관리 도구에서 커밋·병합요청을 작성한 사람. code_change 기반 measure 에만 쓴다.',
       'coalesce(e.author, ''미지정'')', null, null, 'CATEGORY'
 where not exists (select 1 from semantic_dimension where key = 'author');

update semantic_measure
   set allowed_dimensions = array_replace(allowed_dimensions, 'assignee', 'author'),
       updated_at = now()
 where key = 'code_activity_count'
   and 'assignee' = any(allowed_dimensions);
