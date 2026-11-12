-- 진척·지표 결정 반영 (2026-11-12 사용자 결정, IM-007 6절 DEC-01·11·12·19).
--
-- DEC-19 가중치 없는 WBS(L2): 가중치 열이 없으면 계획 기간 비례로 가중치를 매기고 파일의 실적
--   열로 추정 진척률을 낸다. 행을 다시 읽어도 추정인지 알 수 있게 wbs_item 에 표시를 둔다.
--   실적 칸이 비면 actual 을 비워 둔다(0 으로 채우지 않는다). 산출 불가 판단의 재료다.
-- DEC-12 산출물 승인률: 분모는 WBS 가 정한 산출물(말단 작업 중 산출물 열이 있는 것), 분자는 그
--   산출물의 현행 버전이 승인 상태인 것. 판정이 맞춘 산출물 항목을 행에 남겨 SQL 로 센다.
--   예전 지표(work_product_approval_rate, 22종 기준)는 인도 점검표용으로 이름만 분명히 한다.
-- DEC-01 일정 준수율: 기한이 기준일 이전인 마일스톤 중 기한 안에 닫힌 비율. 분자·분모가 같은
--   집합이다. 기한 없는 마일스톤은 빼고, 다시 열렸다 닫힌 것은 마지막 닫힌 날로 본다.
-- DEC-11 명세서에 없는 기존 요구사항: 요구사항 목록을 확정한 사업에서는 이행률 분모에서 뺀다.

alter table wbs_item
  add column weight_estimated boolean not null default false,
  add column deliverable_product_id uuid references work_product(id) on delete set null;

comment on column wbs_item.weight_estimated is
  '가중치를 파일에서 읽지 않고 계획 기간 비례로 산정했다(L2, DEC-19). 진척률에 「추정」이 붙는다';
comment on column wbs_item.deliverable_product_id is
  '산출물 판정이 맞춘 산출물 항목. 승인률 분자는 이 항목 유형의 현행 버전 승인 여부다(DEC-12)';

alter table progress_snapshot
  add column deliverable_approved_count integer,
  add column deliverable_total_count integer;

comment on column progress_snapshot.deliverable_total_count is
  'WBS 가 정한 산출물 수(승인률 분모, DEC-12). V64 전 스냅샷은 비어 있다';

alter table semantic_measure drop constraint ck_semantic_measure__base_table;
alter table semantic_measure add constraint ck_semantic_measure__base_table
  check (base_table in ('requirement','issue','work_product','risk','code_change',
                        'change_request','correction_action','progress_record',
                        'progress_snapshot','wbs_item','v_wbs_completion','milestone'));

-- DEC-12 (b) 산출물 승인률
insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, numerator_expr, denominator_expr, value_type, unit,
                              allowed_dimensions, allowed_filters, default_dimension, status,
                              target_value, basis) values
('deliverable_approval_rate', '산출물 승인률',
 'WBS 가 정한 산출물 중 현행 버전이 승인된 비율(%). "산출물 승인률", "산출물 몇 개 승인됐나" '
 '질문에 사용. 제출률·22종 점검표와 다르다',
 'wbs_item',
 'left join work_product wpm on wpm.id = e.deliverable_product_id '
 'left join work_product wpc on wpc.project_id = e.project_id and wpc.type = wpm.type and wpc.is_current',
 'e.active and e.weight is not null and coalesce(btrim(e.deliverable), '''') <> ''''',
 'round(100.0 * count(*) filter (where wpc.status = ''APPROVED'') / nullif(count(*), 0), 2)',
 'count(*) filter (where wpc.status = ''APPROVED'')',
 'count(*)',
 'RATE_PCT', '%', '{project}', '{project_id__in}', 'project', 'ACTIVE', 90,
 'WBS 말단 작업이 정한 산출물 수를 분모로, 그 산출물로 판정된 항목의 현행 버전이 승인 상태인 '
 '수를 분자로 한다. 예전 버전이 승인돼 있어도 새 버전이 미승인이면 세지 않는다. 산출물 열이 '
 '빈 작업은 분모에서 뺀다. WBS 가 없으면 산출할 수 없다. 올리려면: 제출된 산출물을 발주기관이 '
 '검토해 승인해야 한다. 올리기만 해서는 안 오른다.');

update semantic_measure set
  label = '산출물 22종 승인률',
  description = 'ISO 29110 산출물 22종 점검표에서 승인 완료 비율(%). 인도 점검표용이다. '
                '"22종" 을 묻는 질문에만 쓰고, 그냥 "산출물 승인률" 은 deliverable_approval_rate',
  basis = '적용 대상인 산출물 22종 항목 중 승인 완료(APPROVED) 인 항목 수를 적용 대상 수로 나눈 '
          '값이다. 인도 점검용이며 사업의 산출물 승인률(WBS 가 정한 산출물 기준)과 분모가 다르다. '
          '올리려면: 제출된 산출물을 발주기관이 검토해 승인 상태로 바꿔야 한다.',
  updated_at = now()
where key = 'work_product_approval_rate';

update semantic_measure set
  row_filter = 'e.deliverable_total_count > 0',
  value_expr = '(array_agg(round(100.0 * e.deliverable_approved_count / e.deliverable_total_count, 2) '
               'order by e.snapshot_date desc))[1]',
  basis = '스냅샷별로 WBS 가 정한 산출물 중 현행 버전이 승인된 수를 WBS 산출물 수로 나눈 값이다. '
          '2026-11-12 이전 스냅샷에는 이 값이 없다. 올리려면: 제출된 산출물을 발주기관이 검토해 '
          '승인해야 한다.',
  updated_at = now()
where key = 'snapshot_work_product_approval_pct';

-- DEC-01 (a) 일정 준수율. <TODAY> 는 조립 때 사업 기준일로 바뀐다(app/semantic/builder.py)
insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, numerator_expr, denominator_expr, value_type, unit,
                              allowed_dimensions, allowed_filters, default_dimension, status, basis)
values
('schedule_compliance_rate', '일정 준수율',
 '기한이 지난 마일스톤 중 기한 안에 닫힌 비율(%). "일정 준수율", "마일스톤 지켰나" 질문에 사용. '
 'WBS 계획 대비 편차(schedule_variance_pct)와 다른 지표다',
 'milestone', null,
 'e.due_on is not null and e.due_on < <TODAY>',
 'round(100.0 * count(*) filter (where e.state = ''CLOSED'' and e.closed_at is not null '
 'and (e.closed_at at time zone ''Asia/Seoul'')::date <= e.due_on) / nullif(count(*), 0), 2)',
 'count(*) filter (where e.state = ''CLOSED'' and e.closed_at is not null '
 'and (e.closed_at at time zone ''Asia/Seoul'')::date <= e.due_on)',
 'count(*)',
 'RATE_PCT', '%', '{project}', '{project_id__in}', 'project', 'ACTIVE',
 '기한이 기준일보다 앞선 마일스톤(GitHub 마일스톤·Redmine 버전)을 분모로, 그중 기한 안에 닫힌 '
 '것을 분자로 한다. 분자와 분모는 같은 마일스톤 집합이다. 기한이 없는 마일스톤과 기한이 아직 '
 '안 된 마일스톤은 세지 않는다. 다시 열렸다 닫혔으면 마지막으로 닫힌 날로 본다. 평가 대상이 '
 '없으면 산출할 수 없다. 올리려면: 마일스톤을 기한 안에 닫는다. 늦게 닫은 것은 오르지 않는다.');

-- DEC-11 (a) 이행률 분모: 요구사항 목록을 확정한 사업은 확정 목록에 든 요구사항만
update semantic_measure set
  row_filter = '(e.baseline_id is not null or not exists (select 1 from requirement_baseline rb '
               'where rb.project_id = e.project_id and rb.status = ''CONFIRMED''))',
  basis = basis || ' 요구사항 목록을 확정한 사업은 확정 목록에 든 요구사항만 센다. 명세서에 없는 '
                   '기존 요구사항은 목록에 따로 보이지만 이행률에는 들지 않는다.',
  updated_at = now()
where key = 'requirement_fulfillment_rate';

update semantic_measure set
  basis = basis || ' 요구사항 목록을 확정한 사업은 확정 목록에 든 요구사항만 센다.',
  updated_at = now()
where key = 'snapshot_requirement_fulfillment_pct';

-- DEC-19 대표 진척률 근거에 L2 를 적는다
update semantic_measure set
  basis = '가장 최근 일별 스냅샷의 대표 진척률이다. WBS 에 가중치가 있으면 말단 작업 가중치와 '
          '실적의 가중합(L1)이고, 가중치가 없으면 계획 기간 비례 가중치와 실적의 가중합인 추정(L2)'
          '이다. 둘 다 업체가 계획서에 적은 자기신고 실적이다. 산출물 제출 여부로 실적을 대신하지 '
          '않는다. 스냅샷이 없으면 값이 없다. 올리려면: 용역사가 사업수행계획서(WBS)의 실적 열을 '
          '갱신해 저장소에 커밋해야 한다. 화면에서 고칠 수 없다.',
  updated_at = now()
where key = 'progress_representative_pct';
