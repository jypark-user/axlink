-- 진행 상황 기본 구성용 지표 (2026-11-18 사용자 지시, SWFR.WEB.001).
--
-- 진행 상황 첫 화면에 「WBS·산출물·요구사항 세 기준 진척률을 일별로 한 그래프에」와 「지금 진행 중인
-- 작업」을 두기로 했다. 지표 하나가 위젯 하나라서 세 기준을 한 그래프에 그리려면 기준 자체가 차원이어야
-- 한다. 스냅샷 한 줄을 세 기준으로 펼쳐 「진척 기준」 차원으로 나눈다. 값은 스냅샷에 이미 있는 것을 그대로
-- 쓴다(새로 세지 않는다). 그래서 카드의 WBS 진척률·산출물 승인률·요구사항 이행률 추이와 같은 값이다.
--
-- 「지금 진행 중인 작업」은 WBS 말단 작업 중 시작일이 지났고 실적이 100% 가 아닌 것이다. 기한이 지났는데
-- 안 끝난 작업도 들어간다.

insert into semantic_dimension (key, label, description, select_expr, label_expr, requires_join,
                                value_type, status) values
('progress_metric', '진척 기준',
 'WBS 진척률·산출물 승인률·요구사항 이행률 중 어느 기준인지. 진척 기준별 추이에만 쓴다',
 'pm.metric', null,
 'cross join lateral (values (''WBS 진척률'', e.wbs_actual_pct), (''산출물 승인률'', case when e.deliverable_total_count > 0 then round(100.0 * e.deliverable_approved_count / e.deliverable_total_count, 2) end), (''요구사항 이행률'', case when e.requirement_total_count > 0 then round(100.0 * e.requirement_verified_count / e.requirement_total_count, 2) end)) as pm(metric, pct)',
 'CATEGORY', 'ACTIVE'),
('wbs_task', 'WBS 작업',
 'WBS 말단 작업(번호와 이름)',
 'e.wbs_id || '' '' || e.name', null, null,
 'CATEGORY', 'ACTIVE');

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status, basis) values
('progress_metric_pct', '진척 기준별 진척률',
 'WBS 진척률·산출물 승인률·요구사항 이행률을 진척 기준 차원으로 나눠 한 그림에 그린다. 스냅샷 기준이라 날짜별 추이가 된다. "세 기준 진척률 추이", "WBS·산출물·요구사항 진척을 같이" 질문에 사용',
 'progress_snapshot',
 'cross join lateral (values (''WBS 진척률'', e.wbs_actual_pct), (''산출물 승인률'', case when e.deliverable_total_count > 0 then round(100.0 * e.deliverable_approved_count / e.deliverable_total_count, 2) end), (''요구사항 이행률'', case when e.requirement_total_count > 0 then round(100.0 * e.requirement_verified_count / e.requirement_total_count, 2) end)) as pm(metric, pct)',
 'pm.pct is not null',
 '(array_agg(pm.pct order by e.snapshot_date desc))[1]', 'RATE_PCT', '%',
 '{project,progress_metric,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'progress_metric', 'ACTIVE',
 '일별 스냅샷 한 줄을 세 기준으로 펼친다. WBS 진척률은 WBS 말단 작업의 가중치와 실적으로 계산한 값(업체 신고), '
 '산출물 승인률은 WBS 가 정한 산출물 중 현행 버전이 승인된 비율, 요구사항 이행률은 이행률 범위의 요구사항 중 '
 '검증·인수 상태 비율이다. 구간에 스냅샷이 여럿이면 가장 늦은 날의 값을 쓴다. 스냅샷을 찍지 않은 날은 점이 없다.'),

('wbs_task_actual_pct', '진행 중 작업 실적',
 'WBS 말단 작업 중 시작일이 지났고 실적이 100% 가 아닌 작업의 실적 진척(%). 기한이 지난 미완료 작업도 들어간다. "지금 진행 중인 작업", "어떤 작업을 하고 있나" 질문에 사용',
 'wbs_item', null,
 'e.active and e.weight is not null and e.start_on <= <TODAY> and coalesce(e.actual, 0) < 1',
 'round(100.0 * sum(e.weight * coalesce(e.actual, 0)) / nullif(sum(e.weight), 0), 1)', 'RATE_PCT', '%',
 '{project,wbs_task}',
 '{project_id__in}',
 'wbs_task', 'ACTIVE',
 '업체가 WBS 파일에 적은 실적이다. 작업별로 나누면 그 작업의 실적이고, 나누지 않으면 진행 중 작업들의 가중 평균이다. '
 '시작 전 작업과 실적 100% 작업은 뺀다.');
