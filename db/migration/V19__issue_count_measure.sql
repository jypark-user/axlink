-- 누적 흐름의 본래 질문은 "이슈가 쌓이는 속도가 닫히는 속도를 앞지르는가" 다.
-- 그런데 기존 이슈 지표는 열린 건만 세거나(open_issue_count) 비율이라(issue_resolution_rate)
-- 기간 × 상태로 쌓아 볼 수가 없었다. 기간 축을 허용하는 건수 지표를 하나 둔다.
insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status)
select 'issue_count', '이슈 건수',
       '상태를 가리지 않고 이슈를 셉니다. 기간 축과 함께 쓰면 쌓이고 닫히는 흐름이 보입니다.',
       'issue', join_clause, null,
       'count(*)', 'COUNT', '건',
       array['project', 'contractor_org', 'issue_status', 'issue_severity', 'assignee',
             'period_month', 'period_week', 'period_day'],
       allowed_filters, 'issue_status', 'ACTIVE'
  from semantic_measure
 where key = 'open_issue_count'
   and not exists (select 1 from semantic_measure where key = 'issue_count');
