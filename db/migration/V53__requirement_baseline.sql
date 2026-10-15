-- 요구사항 기준선 1단계 (GH-139, ARC-028)
--
-- 용역사가 명세서를 등록해 추출 결과를 정리·제출하고, 발주기관이 확정한다. 확정 전 목록은
-- requirement 에 쓰지 않는다. 확정 때 코드가 같은 기존 요구사항은 그 행에 붙이고(ID 유지),
-- 새 코드만 새 행으로 만든다. 지우거나 다시 만드는 행은 없다.

create table requirement_baseline (
  id                       uuid         not null default gen_random_uuid(),
  project_id               uuid         not null,
  version                  integer      not null,
  status                   varchar(20)  not null default 'DRAFT',
  document_upload_id       uuid,
  -- 명세서 자체의 표지 정보. 파일이 지워져도 무엇을 기준으로 삼았는지 남긴다
  source_filename          varchar(300) not null,
  source_file_hash         char(64)     not null,
  source_doc_version       varchar(40),
  created_by_user_id       uuid,
  submitted_by_user_id     uuid,
  submitted_at             timestamptz,
  returned_reason          text,
  confirmed_by_user_id     uuid,
  confirmed_by_role        varchar(40),
  confirmed_at             timestamptz,
  -- 확정 때 정해진 결과. 명세서에 없던 기존 코드와 요구사항 생성을 끈 연결
  confirm_result           jsonb,
  created_at               timestamptz  not null default now(),
  updated_at               timestamptz  not null default now(),
  constraint pk_requirement_baseline primary key (id),
  constraint fk_requirement_baseline__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_requirement_baseline__document foreign key (document_upload_id) references document_upload (id) on delete set null,
  constraint fk_requirement_baseline__created_by foreign key (created_by_user_id) references app_user (id) on delete set null,
  constraint fk_requirement_baseline__submitted_by foreign key (submitted_by_user_id) references app_user (id) on delete set null,
  constraint fk_requirement_baseline__confirmed_by foreign key (confirmed_by_user_id) references app_user (id) on delete set null,
  constraint uq_requirement_baseline__version unique (project_id, version),
  constraint ck_requirement_baseline__status check (status in ('DRAFT','SUBMITTED','CONFIRMED')),
  constraint ck_requirement_baseline__confirmed check (
    (status = 'CONFIRMED') = (confirmed_at is not null)),
  constraint ck_requirement_baseline__submitted check (
    status = 'DRAFT' or submitted_at is not null)
);

-- 작업 중(초안·제출)인 것은 사업에 하나, 확정본도 하나(1단계는 최초 기준선만). 같은 확정 요청이
-- 두 번 와도 둘째는 이 제약과 행 잠금에 걸린다
create unique index uq_requirement_baseline__open on requirement_baseline (project_id)
  where status in ('DRAFT','SUBMITTED');
create unique index uq_requirement_baseline__confirmed on requirement_baseline (project_id)
  where status = 'CONFIRMED';

create table requirement_baseline_item (
  id                uuid          not null default gen_random_uuid(),
  baseline_id       uuid          not null,
  seq               integer       not null,
  code              varchar(64),
  title             varchar(500)  not null,
  body              text          not null default '',
  priority          varchar(20)   not null default 'SHOULD',
  -- 명세서 안의 위치. "표 2 · 5행", "41번째 줄". 사람이 손으로 더한 항목은 비어 있다
  source_location   varchar(120),
  -- 추출이 낸 원문 그대로(정리 전). 사람이 고쳐도 남아 무엇을 바꿨는지 보인다
  extracted_json    jsonb,
  origin            varchar(20)   not null default 'EXTRACTED',
  -- 확정 때 정해진다. 붙은 요구사항과 그때의 판정(NEW·SAME·CHANGED)
  requirement_id    uuid,
  match_result      varchar(20),
  spec_applied      boolean       not null default false,
  created_at        timestamptz   not null default now(),
  updated_at        timestamptz   not null default now(),
  constraint pk_requirement_baseline_item primary key (id),
  constraint fk_requirement_baseline_item__baseline foreign key (baseline_id) references requirement_baseline (id) on delete cascade,
  constraint fk_requirement_baseline_item__requirement foreign key (requirement_id) references requirement (id) on delete set null,
  constraint ck_requirement_baseline_item__priority check (priority in ('MUST','SHOULD','COULD','WONT')),
  constraint ck_requirement_baseline_item__origin check (origin in ('EXTRACTED','MANUAL')),
  constraint ck_requirement_baseline_item__match check (match_result is null or match_result in ('NEW','SAME','CHANGED'))
);

create index ix_requirement_baseline_item__baseline on requirement_baseline_item (baseline_id, seq);

-- 기준선에 든 요구사항. 비어 있으면 기준선 밖(이슈에서 만든 것, 명세서에 없던 기존 코드)이다
alter table requirement add column baseline_id uuid;
alter table requirement add column baseline_item_id uuid;
alter table requirement add constraint fk_requirement__baseline
  foreign key (baseline_id) references requirement_baseline (id) on delete set null;
alter table requirement add constraint fk_requirement__baseline_item
  foreign key (baseline_item_id) references requirement_baseline_item (id) on delete set null;

-- 이슈에서 요구사항을 만드는지. 새 연결은 끈다. 이미 있는 연결은 지금 동작(켬)을 이어 가고,
-- 기준선을 확정할 때 끈다(ARC-016 보완)
alter table tool_connection add column requirement_from_issues boolean not null default true;
alter table tool_connection alter column requirement_from_issues set default false;

-- 기준선에 없는 요구사항 코드를 가리킨 근거. 링크 생성 때마다 사업 단위로 다시 쓴다.
-- 버리지 않고 보여 주려고 둔다(QUR.PIP.001: 잇지는 않는다)
create table requirement_unresolved_ref (
  id             uuid          not null default gen_random_uuid(),
  project_id     uuid          not null,
  code           varchar(64)   not null,
  source_type    varchar(40)   not null,
  source_id      uuid          not null,
  evidence_text  text,
  evidence_url   text,
  created_at     timestamptz   not null default now(),
  constraint pk_requirement_unresolved_ref primary key (id),
  constraint fk_requirement_unresolved_ref__project foreign key (project_id) references project (id) on delete cascade,
  constraint uq_requirement_unresolved_ref unique (project_id, code, source_type, source_id)
);

alter table entity_history drop constraint ck_entity_history__entity_type;
alter table entity_history add constraint ck_entity_history__entity_type check (entity_type in (
  'PROJECT','PROJECT_ASSIGNMENT','ORGANIZATION','APP_USER','TOOL_CONNECTION','REQUIREMENT','ISSUE',
  'WORK_PRODUCT','RISK','CODE_CHANGE','TRACE_LINK','CHANGE_REQUEST','CORRECTION_ACTION',
  'PROGRESS_RECORD','ACCEPTANCE_RECORD','DOCUMENT_UPLOAD','REQUIREMENT_BASELINE'));
