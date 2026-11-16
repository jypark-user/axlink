-- 발주기관이 WBS 작업별로 내야 할 산출물과 양식을 정한다 (UC-033, 10-14 협의 1-1절 「WBS 산출물」, GH-141).
--
-- 지금까지 「무엇을 내야 하나」는 용역사가 WBS 파일 산출물 열에 적은 글뿐이었다. 이 표는 발주기관이
-- 정한 항목이다. 항목(무엇을 내나)·양식(어떻게 쓰나)·제출본(낸 버전)·승인(판정)을 나눠 둔다.
--   항목·양식  : 이 표. 양식 파일은 여기 따로 담는다. 문서 표에 넣지 않아 제출본으로 세지 않는다
--   제출본     : document_upload.designated_deliverable_id 로 항목에 잇는다. 확정(DEC-14)해야 제출이다
--   승인·반려  : 지금처럼 제출본의 산출물 버전(work_product)에 붙는다
--
-- 작업은 번호가 아니라 정체(wbs_item.task_key, V46)로 묶는다. 계획서를 다시 올려 정체가 이어지면
-- 지정도 따라가고, 끊기면 「재지정 필요」로 보인다. 지정을 지우지 않는다(active=false + 이력).
-- 22종은 분류일 뿐이다. 필수 목록으로 만들지 않는다.

create table wbs_designated_deliverable (
  id                     uuid         primary key default gen_random_uuid(),
  project_id             uuid         not null references project(id) on delete cascade,
  task_key               uuid         not null,
  wbs_id_at              varchar(40)  not null,   -- 지정·재지정할 때의 번호. 정체가 아니라 표시용
  task_name_at           varchar(500) not null,   -- 그때의 작업명. 작업이 사라져도 무엇이었는지 보인다
  name                   varchar(300) not null,
  description            text,
  product_type           varchar(40),
  guide                  text,
  template_filename      varchar(300),
  template_content_type  varchar(120),
  template_bytes         bytea,
  template_size          integer,
  template_uploaded_at   timestamptz,
  active                 boolean      not null default true,
  created_by_user_id     uuid         not null references app_user(id) on delete restrict,
  created_at             timestamptz  not null default now(),
  updated_at             timestamptz  not null default now(),
  constraint ck_wbs_designated_deliverable__name check (btrim(name) <> ''),
  constraint ck_wbs_designated_deliverable__template check (
    (template_bytes is null) = (template_filename is null)
  ),
  constraint ck_wbs_designated_deliverable__product_type check (product_type is null or product_type in (
    'STATEMENT_OF_WORK','PROJECT_PLAN','PROGRESS_STATUS_RECORD','MEETING_RECORD','CHANGE_REQUEST',
    'CORRECTION_REGISTER','ACCEPTANCE_RECORD','PROJECT_REPOSITORY','REPOSITORY_BACKUP','REQUIREMENTS_SPEC',
    'TRACEABILITY_RECORD','SOFTWARE_DESIGN','TEST_CASES_PROCEDURES','SOFTWARE_COMPONENT','SOFTWARE',
    'TEST_REPORT','PRODUCT_OPERATION_GUIDE','SOFTWARE_USER_DOC','SOFTWARE_CONFIGURATION','MAINTENANCE_DOC',
    'VERIFICATION_RESULTS','VALIDATION_RESULTS'))
);

create index ix_wbs_designated_deliverable__project on wbs_designated_deliverable (project_id, active);
create index ix_wbs_designated_deliverable__task on wbs_designated_deliverable (task_key) where active;

-- 지정 변경 이력. 추가만 한다
create table wbs_designated_deliverable_event (
  id                     uuid         primary key default gen_random_uuid(),
  designated_id          uuid         not null references wbs_designated_deliverable(id) on delete cascade,
  kind                   varchar(20)  not null,
  actor_user_id          uuid         not null references app_user(id) on delete restrict,
  at                     timestamptz  not null default now(),
  detail_json            jsonb        not null default '{}'::jsonb,
  constraint ck_wbs_designated_deliverable_event__kind
    check (kind in ('CREATED','UPDATED','TEMPLATE','REASSIGNED','REMOVED'))
);

create index ix_wbs_designated_deliverable_event__item
  on wbs_designated_deliverable_event (designated_id, at);

-- 제출본이 어느 지정 항목의 것인가. 지정 항목을 골라 올린 문서만 잇는다
alter table document_upload
  add column designated_deliverable_id uuid references wbs_designated_deliverable(id) on delete set null;

create index ix_document_upload__designated on document_upload (designated_deliverable_id)
  where designated_deliverable_id is not null;

comment on table wbs_designated_deliverable is
  '발주기관이 WBS 작업(task_key)별로 정한 제출 산출물 항목과 양식(UC-033). 양식은 제출본이 아니다';
comment on column document_upload.designated_deliverable_id is
  '이 문서가 제출본인 지정 산출물 항목. 확정(초안 확정 = 제출, DEC-14)해야 제출로 센다';
