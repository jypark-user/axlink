-- WBS 항목을 표준 객체로 둔다 (ARC-016).
--
-- 지금까지 WBS 는 올린 계획서 파일을 요청 때마다 다시 읽어 진척률만 냈다. 어느 표도 WBS
-- 항목을 키로 갖지 않아 이슈·산출물·확인 요청이 항목에 붙을 자리가 없었다. 발주기관이 보는
-- 사업의 뼈대는 WBS 이므로 항목을 행으로 남긴다.
--
-- 같은 계획서 버전(work_product_id)에서 한 번 읽어 두면 그 뒤로는 이 표만 본다. 계획서를
-- 다시 올리면 같은 wbs_id 는 갱신되고 빠진 번호는 active=false 로 남는다. 확인 요청이
-- 가리키던 항목이 사라지지 않는다.

create table wbs_item (
  id                 uuid         primary key default gen_random_uuid(),
  project_id         uuid         not null references project(id) on delete cascade,
  wbs_id             varchar(40)  not null,
  parent_wbs_id      varchar(40),
  name               varchar(500) not null,
  deliverable        text,
  start_on           date,
  end_on             date,
  weight             numeric(9,6),          -- null 이면 묶음(상위 항목). 진척 계산에 안 들어간다
  declared_planned   numeric(7,4),          -- 파일에 적힌 계획. 계획선은 기간으로 다시 계산한다
  actual             numeric(7,4),          -- 파일에 적힌 실적. 진척률의 유일한 재료
  line_no            integer      not null default 0,  -- 파일에서의 순서. 화면이 같은 순서로 보인다
  work_product_id    uuid         references work_product(id) on delete set null,
  active             boolean      not null default true,
  created_at         timestamptz  not null default now(),
  updated_at         timestamptz  not null default now(),
  constraint uq_wbs_item__project_wbs unique (project_id, wbs_id)
);

create index ix_wbs_item__project_active on wbs_item (project_id, active, line_no);
