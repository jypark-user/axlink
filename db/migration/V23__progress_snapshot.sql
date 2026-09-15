-- 일별 스냅샷 (SWFR.PIP.005). 추이는 지금 값을 아무리 잘 세어도 나오지 않는다.
-- 어제의 진척률은 어제 세어 둔 값뿐이다. 하루에 한 줄, 핵심 지표만 남긴다.
--
-- WBS 진척은 저장소에서 수집한 xlsx 를 읽어 계산하므로 SQL 로는 못 센다.
-- 그래서 세 갈래 진척(WBS·이슈·산출물)이 위젯으로 나오려면 이 표가 다리다.

create table progress_snapshot (
  id                            uuid          not null default gen_random_uuid(),
  project_id                    uuid          not null,
  snapshot_date                 date          not null,
  -- 진척 (SWFR.PIP.006). level 은 진척률-산정체계의 L1~L4, 근거가 없으면 NONE.
  level                         varchar(10)   not null,
  representative_pct            numeric(6,2),
  wbs_actual_pct                numeric(6,2),
  wbs_planned_pct               numeric(6,2),
  -- 일정 (SWFR.PIP.007). 마일스톤 표준 객체가 없어 WBS 계획선 대비로 본다.
  behind_task_count             integer       not null default 0,
  -- 품질 (SWFR.PIP.008)
  issue_resolved_count          integer       not null default 0,
  issue_total_count             integer       not null default 0,
  requirement_verified_count    integer       not null default 0,
  requirement_total_count       integer       not null default 0,
  risk_closed_count             integer       not null default 0,
  risk_total_count              integer       not null default 0,
  -- 산출물 (SWFR.PIP.009)
  work_product_submitted_count  integer       not null default 0,
  work_product_approved_count   integer       not null default 0,
  work_product_total_count      integer       not null default 0,
  created_at                    timestamptz   not null default now(),
  constraint pk_progress_snapshot primary key (id),
  constraint uq_progress_snapshot__day unique (project_id, snapshot_date),
  constraint fk_progress_snapshot__project foreign key (project_id) references project (id) on delete cascade,
  constraint ck_progress_snapshot__level check (level in ('L1','L2','L3','L4','NONE'))
);

create index ix_progress_snapshot__project_date on progress_snapshot (project_id, snapshot_date desc);

-- 카탈로그가 이 표를 집계 대상으로 알아야 한다.
alter table semantic_measure drop constraint ck_semantic_measure__base_table;
alter table semantic_measure add constraint ck_semantic_measure__base_table check (base_table in (
  'requirement','issue','work_product','risk','code_change','change_request','correction_action',
  'progress_record','progress_snapshot'));

-- 스냅샷 지표. 기간 축 없이 물으면 가장 최근 스냅샷 값이고, 기간 축을 달면 구간별 마지막 값이다.
-- 평균을 내지 않는다. 진척률 30% 와 60% 의 평균 45% 는 어느 날의 사실도 아니다.
insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status) values
('progress_representative_pct', '진척률',
 '대표 진척률(%). WBS 가 있으면 WBS 기준, 없으면 이슈·산출물 순으로 내려간다. 스냅샷 기준',
 'progress_snapshot', null, 'e.representative_pct is not null',
 '(array_agg(e.representative_pct order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('progress_wbs_pct', 'WBS 진척률',
 'WBS 말단 작업의 가중치와 실적으로 계산한 진척률(%). 업체가 신고한 값이다. 스냅샷 기준',
 'progress_snapshot', null, 'e.wbs_actual_pct is not null',
 '(array_agg(e.wbs_actual_pct order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('progress_planned_pct', '계획 진척률',
 'WBS 계획 기간을 오늘 기준으로 안분한 계획선(%). 스냅샷 기준',
 'progress_snapshot', null, 'e.wbs_planned_pct is not null',
 '(array_agg(e.wbs_planned_pct order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('progress_variance_pct', '계획 대비 편차',
 '실적 진척률에서 계획 진척률을 뺀 값(%p). 음수면 지연. 스냅샷 기준',
 'progress_snapshot', null, 'e.wbs_actual_pct is not null and e.wbs_planned_pct is not null',
 '(array_agg(round(e.wbs_actual_pct - e.wbs_planned_pct, 2) order by e.snapshot_date desc))[1]',
 'PCT_POINT', '%p',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('progress_behind_task_count', '지연 작업 수',
 '계획 종료일이 지났는데 실적이 100% 가 아닌 WBS 말단 작업 수. 스냅샷 기준',
 'progress_snapshot', null, null,
 '(array_agg(e.behind_task_count order by e.snapshot_date desc))[1]',
 'COUNT', '건',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('progress_issue_pct', '이슈 해결률(관측)',
 '닫힌 이슈 ÷ 전체 이슈(%). 도구에 남은 상태로 잰 값이라 신고와 대조할 수 있다. 스냅샷 기준',
 'progress_snapshot', null, 'e.issue_total_count > 0',
 '(array_agg(round(100.0 * e.issue_resolved_count / e.issue_total_count, 2) order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('progress_work_product_pct', '산출물 제출률(관측)',
 '제출·승인된 산출물 ÷ 적용 대상 산출물(%). 파일이 실제로 있는가로 잰 값이다. 스냅샷 기준',
 'progress_snapshot', null, 'e.work_product_total_count > 0',
 '(array_agg(round(100.0 * e.work_product_submitted_count / e.work_product_total_count, 2) order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('snapshot_requirement_fulfillment_pct', '요구사항 이행률 추이',
 '검증·인수 완료 요구사항 ÷ 전체(%). 스냅샷 기준이라 날짜별 추이가 된다',
 'progress_snapshot', null, 'e.requirement_total_count > 0',
 '(array_agg(round(100.0 * e.requirement_verified_count / e.requirement_total_count, 2) order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('snapshot_risk_closed_pct', '리스크 처리율 추이',
 '종료된 리스크 ÷ 전체 리스크(%). 스냅샷 기준',
 'progress_snapshot', null, 'e.risk_total_count > 0',
 '(array_agg(round(100.0 * e.risk_closed_count / e.risk_total_count, 2) order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE'),

('snapshot_work_product_approval_pct', '산출물 승인률 추이',
 '승인된 산출물 ÷ 적용 대상 산출물(%). 스냅샷 기준',
 'progress_snapshot', null, 'e.work_product_total_count > 0',
 '(array_agg(round(100.0 * e.work_product_approved_count / e.work_product_total_count, 2) order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE');

update semantic_measure set target_value = 90
 where key in ('snapshot_requirement_fulfillment_pct', 'snapshot_work_product_approval_pct');
