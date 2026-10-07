-- 질의 응답 종류와 권장 질문 (SWFR.RAG.005 · SWFR.RAG.007).
-- 답이 막힌 이유를 한 문구로 뭉치지 않고 종류로 남긴다. 화면은 메시지를 다시 읽어 그리므로
-- 권장 질문도 메시지에 같이 둔다.

alter table message add column finish_reason varchar(30);
alter table message add column suggestions_json jsonb;

alter table message drop constraint ck_message__route_type;
alter table message add constraint ck_message__route_type
  check (route_type is null or route_type in
    ('DOCUMENT','AGGREGATE','MIXED','OVERVIEW','INTENT','CLARIFY'));

-- 일정 진척(계획 대비). 채우는 경로가 없는 progress_record 를 읽어 늘 값이 없었다.
-- 대시보드 추천 구성 두 곳과 저장된 위젯이 이 키를 쓰므로 끄지 않고 일별 스냅샷으로 옮긴다.
-- 값은 계획 대비 편차(progress_variance_pct)와 같은 식이다. 구간마다 마지막 날의 값이고 평균을
-- 내지 않는다(V23).
update semantic_measure set
  description = '실적 진척률에서 계획 진척률(WBS 기간 안분 추정)을 뺀 값(%p). 음수면 계획보다 늦다. '
                '대시보드 카드용 이름이고 값은 계획 대비 편차와 같다. 스냅샷 기준',
  base_table = 'progress_snapshot',
  join_clause = null,
  row_filter = 'e.wbs_actual_pct is not null and e.wbs_planned_pct is not null',
  value_expr = '(array_agg(round(e.wbs_actual_pct - e.wbs_planned_pct, 2) order by e.snapshot_date desc))[1]',
  allowed_dimensions = '{project,period_month,period_week,period_day}',
  allowed_filters = '{project_id__in,period__between,period__in_month,period__last_n_days}',
  basis = '가장 최근 스냅샷(기간 축이 있으면 구간의 마지막 스냅샷)의 WBS 실적 진척률에서 계획 '
          '진척률을 뺀 값이다. 계획 진척률은 말단 작업의 계획 기간을 날짜로 안분한 추정이다. '
          '음수면 계획보다 늦다.',
  updated_at = now()
where key = 'schedule_variance_pct';

-- 모델이 지표를 가를 수 있게 설명을 고친다. 지연 작업 수의 설명은 실제 기준(계획선)과 달랐다.
update semantic_measure set
  description = '계획선(WBS 기간 안분 추정)보다 실적이 뒤진 WBS 말단 작업 수. 스냅샷 기준',
  updated_at = now()
where key = 'progress_behind_task_count';

update semantic_measure set
  description = 'WBS 계획 기간을 기준일까지 날짜로 안분한 계획선(%). 실제 계획값이 아닌 추정이다. 스냅샷 기준',
  updated_at = now()
where key = 'progress_planned_pct';

update semantic_measure set
  description = '보고 진척률에서 계획 진척률(추정)을 뺀 값(%p). 음수면 계획보다 늦다. 스냅샷 기준',
  updated_at = now()
where key = 'progress_variance_pct';

update semantic_measure set
  description = '산출물 목록 중 파일이 제출·승인된 비율(%). 파일이 있는가만 본다. 발주기관의 완료 '
                '확인과 다르다. 스냅샷 기준',
  updated_at = now()
where key = 'progress_work_product_pct';

update semantic_measure set
  description = 'WBS 말단 작업이 정한 산출물 중 제출된 비율(%). 파일이 올라왔는가만 본다. 발주기관의 '
                '완료 확인과 다르다. "산출물은 얼마나 올라왔나" 질문에 사용',
  updated_at = now()
where key = 'wbs_deliverable_submitted_rate';

update semantic_measure set
  description = 'WBS 말단 작업 가중치 중 발주기관이 작업 완료 확인 요청으로 완료를 인정한 작업의 '
                '가중치 비율(%). 보고 진척률·산출물 제출률과 다르다. "완료가 확인된 작업", '
                '"산출물까지 확인된 진척" 질문에 사용',
  updated_at = now()
where key = 'wbs_completion_rate';

-- 완료 확인율. 확인된 작업이 하나도 없으면 sum 이 null 이라 값 없음이 됐다. ARC-019 는
-- "확인이 없으면 0%" 다. 말단 작업이 없을 때만 산출 불가(null)로 둔다.
update semantic_measure set
  value_expr = 'round(100.0 * coalesce(sum(e.weight) filter (where e.completion_status = ''CONFIRMED''), 0) '
               '/ nullif(sum(e.weight), 0), 2)',
  updated_at = now()
where key = 'wbs_completion_rate';

-- 지연 작업 수. WBS 가 없는 날의 스냅샷도 기본값 0 이 들어가 "지연 작업 0건" 으로 읽혔다.
-- 계획선이 있는 날만 센다. 없으면 값 없음이다.
update semantic_measure set
  row_filter = 'e.wbs_planned_pct is not null',
  updated_at = now()
where key = 'progress_behind_task_count';
