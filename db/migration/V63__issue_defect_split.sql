-- 전체 이슈·일반 이슈·결함을 가른다 (DEC-02, SWFR.PIP.008, IM-007 AC-041-10·AC-043-6).
--
-- 지금까지 issue 테이블의 행은 전부 일반 이슈로 셌다. Redmine 결함 트래커의 이슈도 일반
-- 이슈 처리율에 섞여 들어갔다(IM-009 7.3: 일반 이슈 9건이어야 할 것이 11건·7/11).
--
-- 결함 판별은 연결 설정이다. Redmine 은 결함 트래커 이름(defectTracker), GitHub 은 결함
-- 라벨 이름(defectLabel). 기본값은 없다. 설정이 없는 연결의 이슈는 모두 일반 이슈다.
-- 승격이 issue_kind 를 채운다. 이 파일은 기존 행을 고치지 않는다. 지금 결함 설정을 가진
-- 연결이 없으므로 기존 행은 모두 GENERAL 이 맞고, 설정을 넣으면 다음 수집 때 갈린다.
--
-- 이름과 포함 관계:
--   전체 이슈(결함 포함) = 일반 이슈(결함 제외) + 결함
-- 세 값은 각각 따로 보인다. 셋을 더한 합계는 만들지 않는다(중복 합산).
-- 리스크(risk 테이블)와 예전에 요구사항으로 만든 출처 이슈는 처음부터 issue 에 없다.

alter table issue add column issue_kind varchar(20) not null default 'GENERAL';
alter table issue add constraint ck_issue__kind check (issue_kind in ('GENERAL', 'DEFECT'));
create index ix_issue__project_kind on issue (project_id, issue_kind, status);

-- 일별 스냅샷: 결함 건수를 새로 쌓는다. 예전 행은 비워 둔다(소급하지 않는다).
-- issue_resolved_count·issue_total_count 는 이 판부터 일반 이슈(결함 제외)만 센다.
-- 결함 열이 비어 있는 행은 결함을 가르기 전 기준으로 센 값이다.
alter table progress_snapshot add column defect_resolved_count integer;
alter table progress_snapshot add column defect_total_count integer;
comment on column progress_snapshot.issue_total_count is
  '일반 이슈 수. defect_total_count 가 null 인 행(V63 전)은 결함을 가르지 않고 센 값이다';
comment on column progress_snapshot.defect_total_count is
  '결함 수(DEC-02). null 이면 그날은 결함을 가르기 전이다';

-- 차원·필터: 이슈 종류 -----------------------------------------------------------

insert into semantic_dimension (key, label, description, select_expr, label_expr, requires_join,
                                value_type) values
('issue_kind', '이슈 종류',
 '일반 이슈와 결함으로 나눈다. 결함은 연결 설정의 결함 트래커·결함 라벨로 가른다',
 'e.issue_kind',
 'case e.issue_kind when ''DEFECT'' then ''결함'' else ''일반 이슈'' end',
 null, 'CATEGORY');

insert into semantic_filter (key, field, op, label, description, column_expr, value_type,
                             enum_values) values
('issue_kind__in', 'issue_kind', 'IN', '이슈 종류', '일반 이슈 또는 결함으로 한정한다',
 'e.issue_kind', 'ENUM_LIST', '{GENERAL,DEFECT}');

-- 일반 이슈 지표: 결함을 뺀다 ------------------------------------------------------

update semantic_measure
   set row_filter = case when row_filter is null or btrim(row_filter) = ''
                         then 'e.issue_kind = ''GENERAL'''
                         else '(' || row_filter || ') and e.issue_kind = ''GENERAL''' end,
       updated_at = now()
 where key in ('issue_count', 'open_issue_count', 'issue_resolution_rate',
               'issue_avg_resolution_days', 'issue_resolution_days_p50',
               'issue_resolution_days_p90');

update semantic_measure set label = '일반 이슈 건수(결함 제외)',
  description = '결함을 뺀 일반 이슈를 상태를 가리지 않고 셉니다. 기간 축과 함께 쓰면 쌓이고 닫히는 '
                '흐름이 보입니다. 결함까지 넣은 수는 전체 이슈 건수, 결함만은 결함 건수입니다.',
  basis = '리스크·결함·예전에 요구사항으로 만든 출처 이슈 제외. 상태를 가리지 않은 일반 이슈 수다. '
          '전체 이슈(결함 포함) = 일반 이슈(결함 제외) + 결함이다. 세 값을 더해 합계로 쓰지 않는다. '
          '결함 매핑(연결 설정의 결함 트래커·결함 라벨)이 없는 사업은 일반 이슈가 전체 이슈와 같다.'
where key = 'issue_count';

update semantic_measure set label = '열린 일반 이슈 수(결함 제외)', basis =
  '리스크·결함·예전에 요구사항으로 만든 출처 이슈 제외. 해결·종료되지 않은 일반 이슈 수다. '
  '열린 결함은 열린 결함 수로 따로 본다. '
  '줄이려면: 도구에서 이슈를 해결·종료 상태로 바꿔야 한다. 다음 수집 때 반영된다.'
where key = 'open_issue_count';

update semantic_measure set label = '일반 이슈 처리율(결함 제외)', basis =
  '리스크·결함·예전에 요구사항으로 만든 출처 이슈 제외. 해결(RESOLVED) 또는 종료(CLOSED) 상태인 '
  '일반 이슈 수를 전체 일반 이슈 수로 나눈 값이다. 결함은 결함 처리율로 따로 본다. '
  '결함 매핑이 없는 사업은 수집한 이슈 전부를 일반 이슈로 센다. 일반 이슈가 없으면 산출할 수 없다. '
  '올리려면: 도구에서 이슈를 해결·종료 상태로 바꾸면 다음 수집 때 반영된다.'
where key = 'issue_resolution_rate';

update semantic_measure set basis =
  '리스크·결함·예전에 요구사항으로 만든 출처 이슈 제외. 해결된 일반 이슈의 생성부터 해결까지 걸린 '
  '일수의 평균이다. 해결되지 않은 이슈는 들지 않는다. '
  '줄이려면: 이슈를 열어 둔 채 오래 두지 않고 처리 즉시 해결 상태로 바꾼다.'
where key = 'issue_avg_resolution_days';

update semantic_measure set basis =
  '리스크·결함·예전에 요구사항으로 만든 출처 이슈 제외. 해결된 일반 이슈 처리일의 중앙값이다. '
  '절반은 이 안에 닫혔다.'
where key = 'issue_resolution_days_p50';

update semantic_measure set basis =
  '리스크·결함·예전에 요구사항으로 만든 출처 이슈 제외. 해결된 일반 이슈 처리일의 상위 10% 경계다. '
  '평균이 감추는 오래 걸린 꼬리를 본다.'
where key = 'issue_resolution_days_p90';

update semantic_measure set basis =
  '가장 최근 스냅샷의 해결 일반 이슈 수를 전체 일반 이슈 수로 나눈 값이다. 도구 상태로 잰 관측값이라 '
  '신고 진척률과 대조한다. 기준 변경: 2026-11-12(V63)부터 결함을 뺀 일반 이슈만 센다. 그 전 '
  '스냅샷은 결함을 가르지 않고 센 값 그대로 두었다(소급 수정하지 않음).'
where key = 'progress_issue_pct';

-- 새 지표: 전체 이슈(결함 포함)·결함 ------------------------------------------------

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status, basis, numerator_expr, denominator_expr)
select 'all_issue_count', '전체 이슈 건수(결함 포함)',
       '일반 이슈와 결함을 함께 센다. "전체 이슈", "결함 포함 이슈" 질문에 사용. 이슈 종류로 나누면 '
       '일반 이슈와 결함이 각각 보인다',
       'issue', null, null, 'count(*)', 'COUNT', '건',
       array['project', 'contractor_org', 'issue_kind', 'issue_status', 'issue_severity',
             'assignee', 'period_month', 'period_week', 'period_day'],
       array['project_id__in', 'issue_kind__in', 'issue_status__in', 'issue_severity__in',
             'contractor_org_id__in', 'period__last_n_days'],
       'issue_kind', 'ACTIVE',
       '리스크·예전에 요구사항으로 만든 출처 이슈 제외. 결함을 포함한 수집 이슈 전체 수다. '
       '전체 이슈(결함 포함) = 일반 이슈(결함 제외) + 결함이다. 일반 이슈 건수·결함 건수와 더해 '
       '합계로 쓰지 않는다(이미 둘을 포함한다).',
       null, null;

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status, basis, numerator_expr, denominator_expr)
values
('defect_count', '결함 건수',
 '결함으로 분류된 이슈를 상태를 가리지 않고 센다. "결함 몇 건", "버그 수" 질문에 사용',
 'issue', null, 'e.issue_kind = ''DEFECT''', 'count(*)', 'COUNT', '건',
 '{project,contractor_org,issue_status,issue_severity,assignee,period_month,period_week,period_day}',
 '{project_id__in,issue_status__in,issue_severity__in,contractor_org_id__in,period__last_n_days}',
 'issue_status', 'ACTIVE',
 '연결 설정의 결함 트래커(Redmine)·결함 라벨(GitHub)로 분류된 이슈 수다. 결함은 전체 이슈에 '
 '포함되고 일반 이슈에는 들지 않는다. 결함 매핑이 없는 사업은 결함을 가르지 않아 0건이다.',
 null, null),
('open_defect_count', '열린 결함 수',
 '해결·종료되지 않은 결함 수. "미해결 결함" 질문에 사용',
 'issue', null, 'e.issue_kind = ''DEFECT'' and e.status in (''OPEN'',''IN_PROGRESS'')',
 'count(*)', 'COUNT', '건',
 '{project,contractor_org,issue_severity,assignee}',
 '{project_id__in,issue_severity__in,contractor_org_id__in,period__last_n_days}',
 'issue_severity', 'ACTIVE',
 '결함으로 분류된 이슈 가운데 해결·종료되지 않은 수다. 열린 일반 이슈에는 들지 않는다. '
 '줄이려면: 도구에서 결함을 해결·종료 상태로 바꾼다. 다음 수집 때 반영된다.',
 null, null),
('defect_resolution_rate', '결함 처리율',
 '전체 결함 중 해결·종료된 결함 비율(%). "결함 처리율", "버그 해결률" 질문에 사용. '
 '일반 이슈 처리율과 다르다',
 'issue', null, 'e.issue_kind = ''DEFECT''',
 'round(100.0 * count(*) filter (where e.status in (''RESOLVED'',''CLOSED'')) / nullif(count(*), 0), 2)',
 'RATE_PCT', '%',
 '{project,contractor_org,issue_severity,assignee,period_month,period_week,period_day}',
 '{project_id__in,issue_severity__in,contractor_org_id__in,period__between,period__in_month,period__last_n_days}',
 'project', 'ACTIVE',
 '결함으로 분류된 이슈 수를 분모로, 해결(RESOLVED)·종료(CLOSED) 상태인 결함 수를 분자로 한다. '
 '결함은 연결 설정의 결함 트래커(Redmine)·결함 라벨(GitHub)로 가른다. 결함 매핑이 없거나 결함이 '
 '한 건도 없으면 산출할 수 없다. 올리려면: 도구에서 고친 결함을 해결·종료 상태로 바꾼다.',
 'count(*) filter (where e.status in (''RESOLVED'',''CLOSED''))', 'count(*)'),
('snapshot_defect_resolved_pct', '결함 처리율 추이',
 '일별 스냅샷의 결함 처리율. 결함을 가르기 시작한 날부터 쌓인다',
 'progress_snapshot', null, 'e.defect_total_count > 0',
 '(array_agg(round(100.0 * e.defect_resolved_count / e.defect_total_count, 2) order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%',
 '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}',
 'period_day', 'ACTIVE',
 '스냅샷마다 해결·종료 결함 수를 전체 결함 수로 나눈 값이다. 2026-11-12(V63) 전 스냅샷에는 결함 '
 '값이 없어 들지 않는다(소급하지 않음). 결함 매핑이 없거나 결함이 없는 날도 들지 않는다.',
 null, null);
