-- 산출물 승인을 올라온 산출물 단위로 (2026-11-18 사용자 결정, SWFR.PIP.009).
--
-- 승인은 22종 분류별 산출물 버전(work_product)에 붙어 있었다. 분류별로 사업 전체에 현행이 하나뿐이라
-- 두 작업이 같은 분류로 내면 앞의 것이 현행에서 밀려나 승인할 수 없었고, 분류를 알아내지 못한 문서는
-- 승인할 버전 자체가 생기지 않았다. 이제 작업(또는 그 작업의 산출물 양식)에 올린 문서 하나하나가
-- 승인 단위다. 22종 분류와 인도 점검표는 납품 점검용으로 그대로 둔다.
--
-- 산출물 진척은 산출물 양식 기준으로 센다. 작업에 양식이 2개면 분모 2, 하나라도 올라오면 1 이다.
-- 제출률(양식 자리에 올라온 비율)과 승인률(그중 최근 것이 승인된 비율)을 따로 낸다. 양식을 하나도
-- 정하지 않은 사업은 예전처럼 WBS 산출물 열을 단위로 센다(분모가 0 이 되지 않게).

alter table document_upload
  add column review_status        varchar(20),
  add column reviewed_by_user_id  uuid references app_user (id) on delete set null,
  add column reviewed_at          timestamptz,
  add column review_reason        text,
  add constraint ck_document_upload__review_status
    check (review_status is null or review_status in ('SUBMITTED', 'APPROVED', 'REJECTED'));

comment on column document_upload.review_status is
  '작업·양식에 올린 산출물의 검토 상태. 작업과 상관없이 올린 자료는 비어 있다';

-- 이미 작업·양식에 올린 문서는 제출로 본다. 그 문서로 확정한 산출물 버전이 승인·반려됐으면 따른다
update document_upload d
   set review_status = case w.status when 'APPROVED' then 'APPROVED'
                                     when 'REJECTED' then 'REJECTED'
                                     else 'SUBMITTED' end,
       reviewed_by_user_id = case when w.status = 'APPROVED' then w.approved_by_user_id end,
       reviewed_at = case when w.status in ('APPROVED', 'REJECTED') then w.updated_at end,
       review_reason = case when w.status = 'REJECTED' then w.reject_reason end
  from document_upload d0
  left join structuring_draft s on s.document_upload_id = d0.id
  left join work_product w on w.id = s.work_product_id
 where d.id = d0.id
   and (d0.wbs_item_id is not null or d0.designated_deliverable_id is not null);

alter table progress_snapshot add column deliverable_submitted_count integer;

-- 산출물 진척의 셈 단위. 양식이 있는 사업은 양식마다 한 줄(그 양식에 가장 최근 올라온 문서의 상태),
-- 없는 사업은 WBS 산출물 열이 있는 말단 작업마다 한 줄(판정과 현행 버전 승인)이다.
create view v_deliverable_unit as
with designated as (
  select dd.project_id, dd.id as unit_id, w.task_key, w.wbs_id, w.end_on, ld.review_status
    from wbs_designated_deliverable dd
    join wbs_item w on w.project_id = dd.project_id and w.task_key = dd.task_key
                   and w.active and w.weight is not null
    left join lateral (
      select d.review_status
        from document_upload d
       where d.designated_deliverable_id = dd.id and d.review_status is not null
       order by d.created_at desc
       limit 1
    ) ld on true
   where dd.active
), plain as (
  -- 작업에 올린 산출물의 승인이 먼저고, 없으면 예전처럼 판정과 현행 버전 승인을 본다
  select w.project_id, w.id as unit_id, w.task_key, w.wbs_id, w.end_on,
         case when ld.review_status = 'APPROVED' or wpc.status = 'APPROVED' then 'APPROVED'
              when ld.review_status = 'REJECTED' then 'REJECTED'
              when w.deliverable_status = 'SUBMITTED' then 'SUBMITTED' end as review_status
    from wbs_item w
    left join work_product wpm on wpm.id = w.deliverable_product_id
    left join work_product wpc on wpc.project_id = w.project_id and wpc.type = wpm.type
                              and wpc.is_current
    left join lateral (
      select d.review_status
        from document_upload d
       where d.wbs_item_id = w.id and d.review_status is not null
       order by d.created_at desc
       limit 1
    ) ld on true
   where w.active and w.weight is not null and coalesce(btrim(w.deliverable), '') <> ''
     and not exists (select 1 from designated x where x.project_id = w.project_id)
)
select project_id, 'FORM' as basis, unit_id, task_key, wbs_id, end_on, review_status,
       coalesce(review_status in ('SUBMITTED', 'APPROVED'), false) as submitted,
       coalesce(review_status = 'APPROVED', false) as approved
  from designated
union all
select project_id, 'WBS', unit_id, task_key, wbs_id, end_on, review_status,
       coalesce(review_status in ('SUBMITTED', 'APPROVED'), false),
       coalesce(review_status = 'APPROVED', false)
  from plain;

alter table semantic_measure drop constraint ck_semantic_measure__base_table;
alter table semantic_measure add constraint ck_semantic_measure__base_table
  check (base_table in ('requirement','issue','work_product','risk','code_change',
                        'change_request','correction_action','progress_record',
                        'progress_snapshot','wbs_item','v_wbs_completion','milestone',
                        'v_deliverable_unit'));

update semantic_measure
   set description = '산출물 양식(없으면 WBS 산출물) 중 가장 최근 올라온 산출물이 승인된 비율(%). "산출물 승인률", "산출물 몇 개 승인됐나" 질문에 사용. 제출률·22종 점검표와 다르다',
       base_table = 'v_deliverable_unit', join_clause = null, row_filter = null,
       value_expr = 'round(100.0 * count(*) filter (where e.approved) / nullif(count(*), 0), 2)',
       numerator_expr = 'count(*) filter (where e.approved)', denominator_expr = 'count(*)',
       basis = '산출물 양식 하나를 한 건으로 센다. 작업에 양식이 2개면 2건이다. 양식마다 가장 최근 올라온 산출물이 '
               '발주기관 승인이면 승인이다. 양식을 정하지 않은 사업은 WBS 산출물 열이 있는 작업마다 한 건이고 '
               '현행 버전 승인을 본다.',
       updated_at = now()
 where key = 'deliverable_approval_rate';

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status, basis, numerator_expr,
                              denominator_expr) values
('deliverable_submission_rate', '산출물 제출률',
 '산출물 양식(없으면 WBS 산출물) 중 산출물이 올라온 비율(%). 반려된 것은 뺀다. "산출물 제출률", "산출물 몇 개 냈나" 질문에 사용. 승인률과 다르다',
 'v_deliverable_unit', null, null,
 'round(100.0 * count(*) filter (where e.submitted) / nullif(count(*), 0), 2)', 'RATE_PCT', '%',
 '{project}', '{project_id__in}', 'project', 'ACTIVE',
 '산출물 양식 하나를 한 건으로 센다. 작업에 양식이 2개면 2건이고 하나만 올라와도 1건이 제출이다. 가장 최근 '
 '올라온 산출물이 반려면 제출로 세지 않는다. 양식을 정하지 않은 사업은 WBS 산출물 열이 있는 작업마다 한 건이다.',
 'count(*) filter (where e.submitted)', 'count(*)'),
('snapshot_deliverable_submission_pct', '산출물 제출률 추이',
 '산출물 양식 중 산출물이 올라온 비율(%). 스냅샷 기준',
 'progress_snapshot', null, 'e.deliverable_total_count > 0 and e.deliverable_submitted_count is not null',
 '(array_agg(round(100.0 * e.deliverable_submitted_count / e.deliverable_total_count, 2) order by e.snapshot_date desc))[1]',
 'RATE_PCT', '%', '{project,period_month,period_week,period_day}',
 '{project_id__in,period__between,period__in_month,period__last_n_days}', 'period_day', 'ACTIVE',
 '일별 스냅샷에 남긴 산출물 제출 수 ÷ 셈 단위 수. 이 값을 남기기 전 스냅샷에는 점이 없다.', null, null);

-- 진척 기준 차원에 산출물 제출률을 더한다(네 기준)
update semantic_dimension
   set description = 'WBS 진척률·산출물 제출률·산출물 승인률·요구사항 이행률 중 어느 기준인지. 진척 기준별 추이에만 쓴다',
       requires_join = 'cross join lateral (values (''WBS 진척률'', e.wbs_actual_pct), (''산출물 제출률'', case when e.deliverable_total_count > 0 and e.deliverable_submitted_count is not null then round(100.0 * e.deliverable_submitted_count / e.deliverable_total_count, 2) end), (''산출물 승인률'', case when e.deliverable_total_count > 0 then round(100.0 * e.deliverable_approved_count / e.deliverable_total_count, 2) end), (''요구사항 이행률'', case when e.requirement_total_count > 0 then round(100.0 * e.requirement_verified_count / e.requirement_total_count, 2) end)) as pm(metric, pct)'
 where key = 'progress_metric';

update semantic_measure
   set join_clause = (select requires_join from semantic_dimension where key = 'progress_metric'),
       description = 'WBS 진척률·산출물 제출률·산출물 승인률·요구사항 이행률을 진척 기준 차원으로 나눠 한 그림에 그린다. 스냅샷 기준이라 날짜별 추이가 된다. "기준별 진척률 추이", "WBS·산출물·요구사항 진척을 같이" 질문에 사용',
       updated_at = now()
 where key = 'progress_metric_pct';
