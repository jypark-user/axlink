-- 예상 산출물: WBS 산출물과 발주기관 요청을 둘 다 센다 (11-19 사용자 결정)
--
-- 예상 산출물은 WBS 산출물 열의 이름(작업마다 하나)과 발주기관이 요청한 산출물들이다. 한 작업에
-- 둘 다 있으면 둘 다 한 건씩이다. V71 은 요청이 있으면 WBS 쪽을 뺐다.
-- WBS 쪽은 요청에 매이지 않고 그 작업에 올라온 산출물 중 가장 최근 것의 검토 상태를 본다.

create or replace view v_deliverable_unit as
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
  select w.project_id, w.id as unit_id, w.task_key, w.wbs_id, w.end_on, ld.review_status
    from wbs_item w
    left join lateral (
      select d.review_status
        from document_upload d
       where d.wbs_item_id = w.id and d.designated_deliverable_id is null
         and d.review_status is not null
       order by d.created_at desc
       limit 1
    ) ld on true
   where w.active and w.weight is not null and coalesce(btrim(w.deliverable), '') <> ''
)
select project_id, 'FORM' as basis, unit_id, task_key, wbs_id, end_on,
       review_status::varchar as review_status,
       coalesce(review_status in ('SUBMITTED', 'APPROVED'), false) as submitted,
       coalesce(review_status = 'APPROVED', false) as approved
  from designated
union all
select project_id, 'WBS', unit_id, task_key, wbs_id, end_on, review_status::varchar,
       coalesce(review_status in ('SUBMITTED', 'APPROVED'), false),
       coalesce(review_status = 'APPROVED', false)
  from plain;

update semantic_measure
   set description = '예상 산출물 중 가장 최근 올라온 산출물이 승인된 비율(%). "산출물 승인률", "산출물 몇 개 승인됐나" 질문에 사용. 제출률·22종 점검표와 다르다',
       basis = '예상 산출물 하나를 한 건으로 센다. 예상 산출물은 WBS 산출물 열의 이름과 발주기관이 요청한 '
               '산출물이다(둘 다 있으면 둘 다). 가장 최근 올라온 산출물이 발주기관 승인이면 승인이다.',
       updated_at = now()
 where key = 'deliverable_approval_rate';

update semantic_measure
   set description = '예상 산출물 중 산출물이 올라온 비율(%). 반려된 것은 뺀다. "산출물 제출률", "산출물 몇 개 냈나" 질문에 사용. 승인률과 다르다',
       basis = '예상 산출물 하나를 한 건으로 센다. 예상 산출물은 WBS 산출물 열의 이름과 발주기관이 요청한 '
               '산출물이다(둘 다 있으면 둘 다). 가장 최근 올라온 산출물이 반려면 제출로 세지 않는다.',
       updated_at = now()
 where key = 'deliverable_submission_rate';
