-- 인포그래픽이 더 말하게 하려면 값만으로는 모자란다.
-- 비율에는 목표가, 활동에는 날짜 축이, 처리일에는 분포가 있어야 한다.

-- 1) 새 그림 9종도 위젯으로 저장할 수 있어야 한다.
alter table widget drop constraint ck_widget__template;
alter table widget add constraint ck_widget__template check (template in (
  'STAT_CARD','BAR_CHART','LINE_CHART','PIE_CHART','PROGRESS_LIST','DATA_TABLE',
  'CHECKLIST','GANTT_SUMMARY','STATUS_FLOW','HEATMAP',
  'AREA_CHART','STACKED_BAR_CHART','HORIZONTAL_BAR_CHART','DONUT_CHART','RADAR_CHART',
  'CUMULATIVE_FLOW','PARETO','TREEMAP','SLOPE_CHART','BUMP_CHART','SPARKLINE',
  'BULLET_CHART','CALENDAR_HEATMAP'));

-- 2) 목표값. 이행률 82% 는 그 자체로는 좋은지 나쁜지 알 수 없다.
alter table semantic_measure add column if not exists target_value numeric;

update semantic_measure set target_value = 90 where key = 'requirement_fulfillment_rate';
update semantic_measure set target_value = 90 where key = 'work_product_approval_rate';
update semantic_measure set target_value = 95 where key = 'test_pass_rate';
update semantic_measure set target_value = 80 where key = 'requirement_test_trace_rate';
update semantic_measure set target_value = 85 where key = 'issue_resolution_rate';

-- 3) 일 단위 기간 축. 커밋·MR 활동의 빈 날을 보려면 월·주 눈금은 굵다.
insert into semantic_dimension (key, label, description, select_expr, value_type, status)
select 'period_day', '일', '일 단위 기간 축입니다.',
       'to_char(date_trunc(''day'', <TIME_COL>), ''YYYY-MM-DD'')', 'TIME', 'ACTIVE'
 where not exists (select 1 from semantic_dimension where key = 'period_day');

-- 월 축을 쓰는 지표는 일 축도 쓸 수 있다.
update semantic_measure
   set allowed_dimensions = allowed_dimensions || array['period_day']
 where 'period_month' = any(allowed_dimensions)
   and not ('period_day' = any(allowed_dimensions));

-- 4) 처리일 분포. 평균 하나로는 "대부분 이틀, 몇 건은 서른 날" 이 보이지 않는다.
insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status)
select 'issue_resolution_days_p50', '이슈 처리일 중앙값',
       '이슈 절반이 이 날짜 안에 닫힙니다.',
       base_table, join_clause, row_filter,
       'round(percentile_cont(0.5) within group (order by '
       || 'extract(epoch from (e.resolved_at - e.source_created_at)) / 86400.0)::numeric, 2)',
       value_type, unit, allowed_dimensions, allowed_filters, default_dimension, 'ACTIVE'
  from semantic_measure
 where key = 'issue_avg_resolution_days'
   and not exists (select 1 from semantic_measure where key = 'issue_resolution_days_p50');

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status)
select 'issue_resolution_days_p90', '이슈 처리일 상위 10%',
       '늦게 닫힌 열 건 중 한 건은 이만큼 걸립니다 — 평균이 감추는 꼬리입니다.',
       base_table, join_clause, row_filter,
       'round(percentile_cont(0.9) within group (order by '
       || 'extract(epoch from (e.resolved_at - e.source_created_at)) / 86400.0)::numeric, 2)',
       value_type, unit, allowed_dimensions, allowed_filters, default_dimension, 'ACTIVE'
  from semantic_measure
 where key = 'issue_avg_resolution_days'
   and not exists (select 1 from semantic_measure where key = 'issue_resolution_days_p90');
