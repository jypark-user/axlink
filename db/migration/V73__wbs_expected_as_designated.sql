-- WBS 산출물을 예상 산출물 항목으로 남긴다 (11-19 사용자 결정)
--
-- 예상 산출물 목록에 WBS 산출물 열에서 온 것(「WBS 자동」)과 발주기관이 요청한 것이 같이 보이고,
-- WBS 에서 온 것도 고치기로 이름·설명·양식 파일을 붙일 수 있어야 한다. 그래서 WBS 산출물도
-- wbs_designated_deliverable 의 행으로 둔다(origin = 'WBS'). 만든 사람은 없다(시스템).
-- 작업마다 WBS 행은 하나다. 발주기관이 거두면 비활성으로 남고 다시 만들지 않는다.

alter table wbs_designated_deliverable
  add column origin       varchar(10)  not null default 'REQUEST',
  add column wbs_name_at  varchar(300),
  alter column created_by_user_id drop not null,
  add constraint ck_wbs_designated_deliverable__origin check (origin in ('REQUEST', 'WBS')),
  add constraint ck_wbs_designated_deliverable__creator
    check (origin = 'WBS' or created_by_user_id is not null);

comment on column wbs_designated_deliverable.origin is
  'REQUEST: 발주기관이 요청한 산출물. WBS: WBS 산출물 열에서 저절로 만든 예상 산출물';
comment on column wbs_designated_deliverable.wbs_name_at is
  'WBS 행이 마지막으로 따른 산출물 열 값. 이름을 고치지 않았으면 열이 바뀔 때 이름도 따라간다';

create unique index uq_wbs_designated_deliverable__wbs_task
  on wbs_designated_deliverable (project_id, task_key) where origin = 'WBS';

-- 지금 계획서의 말단 작업마다 WBS 행을 만든다
insert into wbs_designated_deliverable
  (project_id, task_key, wbs_id_at, task_name_at, name, origin, wbs_name_at)
select w.project_id, w.task_key, w.wbs_id, w.name, left(btrim(w.deliverable), 300), 'WBS',
       left(btrim(w.deliverable), 300)
  from wbs_item w
 where w.active and w.weight is not null and w.task_key is not null
   and coalesce(btrim(w.deliverable), '') <> ''
on conflict do nothing;

-- 요청에 매이지 않고 작업에 올라온 산출물은 그 작업의 WBS 행에 잇는다(V72 의 WBS 셈과 같은 근거)
update document_upload d
   set designated_deliverable_id = dd.id
  from wbs_item w
  join wbs_designated_deliverable dd
    on dd.project_id = w.project_id and dd.task_key = w.task_key and dd.origin = 'WBS'
 where d.wbs_item_id = w.id and d.designated_deliverable_id is null
   and d.review_status is not null;

-- 셈은 이제 항목 하나가 한 건이다. basis 는 출처를 적는다
create or replace view v_deliverable_unit as
with unit as (
  select dd.project_id, dd.id as unit_id, dd.origin, w.task_key, w.wbs_id, w.end_on,
         ld.review_status
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
)
select project_id, case origin when 'WBS' then 'WBS' else 'FORM' end as basis, unit_id,
       task_key, wbs_id, end_on, review_status::varchar as review_status,
       coalesce(review_status in ('SUBMITTED', 'APPROVED'), false) as submitted,
       coalesce(review_status = 'APPROVED', false) as approved
  from unit;
