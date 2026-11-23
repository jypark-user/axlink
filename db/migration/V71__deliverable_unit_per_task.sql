-- 요청 산출물 셈을 작업마다 정한다 (11-19 사용자 결정)
--
-- 발주기관이 요청 산출물(옛 이름 산출물 양식)을 등록한 작업은 그 항목 하나하나가 한 건이다.
-- 등록이 없는 작업도 WBS 산출물 열에 이름이 있으면 그 이름이 요청 산출물 한 건이다(양식 파일 없음).
-- 둘 다 없는 작업은 셈에 들지 않는다.
--
-- V70 은 사업 단위로 갈랐다(양식이 하나라도 있으면 양식만, 없으면 WBS 만). 그러면 양식을 몇 작업에만
-- 단 사업에서 나머지 작업의 WBS 산출물이 셈에서 빠졌다. 또 저장소 파일 자동 판정이 없어져
-- (11-19) WBS 쪽도 그 작업에 올라온 산출물의 검토 상태만 본다. 22종 현행 버전 승인은 보지 않는다.

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
       where d.wbs_item_id = w.id and d.review_status is not null
       order by d.created_at desc
       limit 1
    ) ld on true
   where w.active and w.weight is not null and coalesce(btrim(w.deliverable), '') <> ''
     and not exists (
       select 1 from designated x where x.project_id = w.project_id and x.task_key = w.task_key
     )
)
-- review_status 는 V70 과 같은 형(길이 없는 varchar)으로 둔다. 뷰 열 형을 바꿀 수 없다
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
   set description = '요청 산출물 중 가장 최근 올라온 산출물이 승인된 비율(%). "산출물 승인률", "산출물 몇 개 승인됐나" 질문에 사용. 제출률·22종 점검표와 다르다',
       basis = '요청 산출물 하나를 한 건으로 센다. 작업에 요청 산출물이 2개면 2건이다. 등록이 없는 작업은 WBS '
               '산출물 열의 이름이 한 건이다. 가장 최근 올라온 산출물이 발주기관 승인이면 승인이다.',
       updated_at = now()
 where key = 'deliverable_approval_rate';

update semantic_measure
   set description = '요청 산출물 중 산출물이 올라온 비율(%). 반려된 것은 뺀다. "산출물 제출률", "산출물 몇 개 냈나" 질문에 사용. 승인률과 다르다',
       basis = '요청 산출물 하나를 한 건으로 센다. 작업에 요청 산출물이 2개면 2건이고 하나만 올라와도 1건이 '
               '제출이다. 등록이 없는 작업은 WBS 산출물 열의 이름이 한 건이다. 가장 최근 올라온 산출물이 '
               '반려면 제출로 세지 않는다.',
       updated_at = now()
 where key = 'deliverable_submission_rate';
