-- AX-Link 초기 스키마. 근거: docs/design/02-logical-datamodel.md
-- 실행 대상: PostgreSQL 14 + pgvector 0.8.0

create extension if not exists vector;
create extension if not exists pg_trgm;
create extension if not exists pgcrypto;

-- ============================================================
-- 1. IAM
-- ============================================================

create table organization (
  id            uuid         not null default gen_random_uuid(),
  name          varchar(200) not null,
  type          varchar(40)  not null,
  business_no   varchar(20),
  status        varchar(40)  not null default 'ACTIVE',
  created_at    timestamptz  not null default now(),
  updated_at    timestamptz  not null default now(),
  constraint pk_organization primary key (id),
  constraint uq_organization__name unique (name),
  constraint ck_organization__type check (type in ('CLIENT','CONTRACTOR')),
  constraint ck_organization__status check (status in ('ACTIVE','DISABLED'))
);

create table app_user (
  id              uuid         not null default gen_random_uuid(),
  organization_id uuid         not null,
  email           varchar(254) not null,
  name            varchar(200) not null,
  password_hash   varchar(72),
  role            varchar(40)  not null,
  status          varchar(40)  not null default 'INVITED',
  last_login_at   timestamptz,
  created_at      timestamptz  not null default now(),
  updated_at      timestamptz  not null default now(),
  constraint pk_app_user primary key (id),
  constraint fk_app_user__organization foreign key (organization_id) references organization (id) on delete restrict,
  constraint ck_app_user__role check (role in ('SUPER_ADMIN','CLIENT','CONTRACTOR')),
  constraint ck_app_user__status check (status in ('INVITED','ACTIVE','DISABLED'))
);

create unique index uq_app_user__email on app_user (lower(email));
create index ix_app_user__organization on app_user (organization_id);

create table user_invitation (
  id                 uuid        not null default gen_random_uuid(),
  app_user_id        uuid        not null,
  token_hash         char(64)    not null,
  expires_at         timestamptz not null,
  accepted_at        timestamptz,
  invited_by_user_id uuid        not null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint pk_user_invitation primary key (id),
  constraint uq_user_invitation__token_hash unique (token_hash),
  constraint fk_user_invitation__app_user foreign key (app_user_id) references app_user (id) on delete cascade,
  constraint fk_user_invitation__invited_by foreign key (invited_by_user_id) references app_user (id) on delete restrict
);

create index ix_user_invitation__user on user_invitation (app_user_id);

create table refresh_token (
  id          uuid         not null default gen_random_uuid(),
  app_user_id uuid         not null,
  token_hash  char(64)     not null,
  expires_at  timestamptz  not null,
  revoked_at  timestamptz,
  user_agent  varchar(300),
  created_at  timestamptz  not null default now(),
  constraint pk_refresh_token primary key (id),
  constraint uq_refresh_token__token_hash unique (token_hash),
  constraint fk_refresh_token__app_user foreign key (app_user_id) references app_user (id) on delete cascade
);

create index ix_refresh_token__user_expires on refresh_token (app_user_id, expires_at desc);

-- ============================================================
-- 2. PRJ
-- ============================================================

create table project (
  id               uuid         not null default gen_random_uuid(),
  client_org_id    uuid         not null,
  name             varchar(200) not null,
  start_date       date         not null,
  end_date         date         not null,
  description      text         not null,
  status           varchar(40)  not null default 'PLANNING',
  current_si_phase varchar(40),
  closed_at        timestamptz,
  created_at       timestamptz  not null default now(),
  updated_at       timestamptz  not null default now(),
  constraint pk_project primary key (id),
  constraint uq_project__client_name unique (client_org_id, name),
  constraint fk_project__organization foreign key (client_org_id) references organization (id) on delete restrict,
  constraint ck_project__status check (status in ('PLANNING','ACTIVE','CLOSING','CLOSED')),
  constraint ck_project__period check (start_date <= end_date),
  constraint ck_project__description check (length(btrim(description)) > 0),
  constraint ck_project__si_phase check (current_si_phase is null or current_si_phase in ('SI_1','SI_2','SI_3','SI_4','SI_5','SI_6')),
  constraint ck_project__closed_at check ((status = 'CLOSED') = (closed_at is not null))
);

create index ix_project__client_org_status on project (client_org_id, status);

create table project_assignment (
  id                  uuid        not null default gen_random_uuid(),
  project_id          uuid        not null,
  contractor_org_id   uuid        not null,
  user_id             uuid        not null,
  permissions_json    jsonb       not null default '{"canConfigureIntegration":false,"canUploadDocument":false,"canReadDashboard":false}'::jsonb,
  status              varchar(40) not null default 'ACTIVE',
  assigned_by_user_id uuid        not null,
  revoked_at          timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint pk_project_assignment primary key (id),
  constraint fk_project_assignment__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_project_assignment__organization foreign key (contractor_org_id) references organization (id) on delete restrict,
  constraint fk_project_assignment__app_user foreign key (user_id) references app_user (id) on delete cascade,
  constraint fk_project_assignment__assigned_by foreign key (assigned_by_user_id) references app_user (id) on delete restrict,
  constraint ck_project_assignment__status check (status in ('ACTIVE','REVOKED'))
);

create unique index uq_project_assignment__active on project_assignment (project_id, user_id) where status = 'ACTIVE';
create index ix_project_assignment__user_status on project_assignment (user_id, status);
create index ix_project_assignment__project on project_assignment (project_id);

-- ============================================================
-- 3. INT
-- ============================================================

create table tool_connection (
  id                        uuid         not null default gen_random_uuid(),
  project_id                uuid         not null,
  contractor_org_id         uuid         not null,
  tool                      varchar(40)  not null,
  name                      varchar(200) not null,
  base_url                  text         not null,
  target_resource           varchar(300) not null,
  auth_encrypted            text         not null,
  auth_hint                 varchar(20)  not null,
  mapping_rules_json        jsonb        not null default '{"version":1,"rules":[]}'::jsonb,
  webhook_secret_encrypted  text,
  status                    varchar(40)  not null default 'DRAFT',
  last_verified_at          timestamptz,
  last_synced_at            timestamptz,
  last_sync_cursor          varchar(300),
  last_error                text,
  created_at                timestamptz  not null default now(),
  updated_at                timestamptz  not null default now(),
  constraint pk_tool_connection primary key (id),
  constraint uq_tool_connection__target unique (project_id, tool, target_resource),
  constraint fk_tool_connection__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_tool_connection__organization foreign key (contractor_org_id) references organization (id) on delete restrict,
  constraint ck_tool_connection__tool check (tool in ('JIRA','GITLAB','NOTION','REDMINE')),
  constraint ck_tool_connection__status check (status in ('DRAFT','VERIFIED','ACTIVE','PAUSED','FAILED'))
);

create index ix_tool_connection__poll on tool_connection (status, last_synced_at);
create index ix_tool_connection__contractor_org on tool_connection (contractor_org_id);

create table sync_job (
  id                 uuid        not null default gen_random_uuid(),
  tool_connection_id uuid        not null,
  kind               varchar(40) not null,
  status             varchar(40) not null default 'QUEUED',
  cursor_from        timestamptz,
  cursor_to          timestamptz,
  started_at         timestamptz,
  finished_at        timestamptz,
  stats_json         jsonb       not null default '{}'::jsonb,
  error_code         varchar(40),
  error              text,
  retry_of_job_id    uuid,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint pk_sync_job primary key (id),
  constraint fk_sync_job__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete cascade,
  constraint fk_sync_job__retry_of foreign key (retry_of_job_id) references sync_job (id) on delete set null,
  constraint ck_sync_job__kind check (kind in ('BACKFILL','POLL','WEBHOOK')),
  constraint ck_sync_job__status check (status in ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  constraint ck_sync_job__error_code check (error_code is null or error_code in (
    'AI_UNAVAILABLE','TOOL_AUTH_FAILED','TOOL_RESOURCE_NOT_FOUND','TOOL_RATE_LIMITED','TOOL_UNAVAILABLE',
    'CATALOG_VALIDATION_FAILED','PROJECT_ACCESS_DENIED','WORK_PRODUCT_TYPE_REJECTED',
    'EMBEDDING_DIMENSION_MISMATCH','DOCUMENT_PARSE_FAILED','INTERNAL_ERROR'))
);

create unique index uq_sync_job__running on sync_job (tool_connection_id) where status = 'RUNNING';
create index ix_sync_job__connection_started on sync_job (tool_connection_id, started_at desc);
create index ix_sync_job__retention on sync_job (status, finished_at);

create table raw_artifact (
  id                 uuid         not null default gen_random_uuid(),
  tool_connection_id uuid         not null,
  external_id        varchar(255) not null,
  object_kind        varchar(60)  not null,
  payload_jsonb      jsonb        not null,
  content_hash       char(64)     not null,
  fetched_at         timestamptz  not null default now(),
  sync_job_id        uuid,
  created_at         timestamptz  not null default now(),
  constraint pk_raw_artifact primary key (id),
  constraint uq_raw_artifact__source unique (tool_connection_id, external_id),
  constraint fk_raw_artifact__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete cascade,
  constraint fk_raw_artifact__sync_job foreign key (sync_job_id) references sync_job (id) on delete set null,
  constraint ck_raw_artifact__payload check (jsonb_typeof(payload_jsonb) = 'object')
);

create index ix_raw_artifact__hash on raw_artifact (tool_connection_id, content_hash);
create index ix_raw_artifact__sync_job on raw_artifact (sync_job_id);

create table document_upload (
  id                   uuid         not null default gen_random_uuid(),
  project_id           uuid         not null,
  uploaded_by_user_id  uuid         not null,
  original_filename    varchar(300) not null,
  stored_path          varchar(300) not null,
  content_type         varchar(120) not null,
  file_ext             varchar(40)  not null,
  size_bytes           bigint       not null,
  file_hash            char(64)     not null,
  extracted_text       text,
  page_count           integer,
  status               varchar(40)  not null default 'UPLOADED',
  error                text,
  created_at           timestamptz  not null default now(),
  updated_at           timestamptz  not null default now(),
  constraint pk_document_upload primary key (id),
  constraint uq_document_upload__file unique (project_id, file_hash),
  constraint fk_document_upload__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_document_upload__uploaded_by foreign key (uploaded_by_user_id) references app_user (id) on delete restrict,
  constraint ck_document_upload__file_ext check (file_ext in ('HWP','HWPX','DOCX','XLSX','PDF')),
  constraint ck_document_upload__status check (status in ('UPLOADED','EXTRACTED','STRUCTURED','CONFIRMED','REJECTED','FAILED')),
  constraint ck_document_upload__size check (size_bytes > 0 and size_bytes <= 104857600)
);

create index ix_document_upload__project_status on document_upload (project_id, status);

-- ============================================================
-- 4. STD — ISO/IEC 29110 표준 엔티티
-- ============================================================

create table work_product (
  id                   uuid         not null default gen_random_uuid(),
  project_id           uuid         not null,
  type                 varchar(40)  not null,
  version              varchar(40)  not null default '0',
  title                varchar(500),
  status               varchar(40)  not null default 'NONE',
  applicable           boolean      not null default true,
  is_current           boolean      not null default true,
  pm_activity          varchar(40),
  si_activity          varchar(40),
  document_upload_id   uuid,
  file_uri             text,
  authored_at          date,
  submitted_at         timestamptz,
  approved_by_user_id  uuid,
  approved_at          timestamptz,
  reject_reason        text,
  tool_connection_id   uuid,
  external_id          varchar(255),
  external_url         text,
  source_kind          varchar(40)  not null default 'MANUAL',
  created_at           timestamptz  not null default now(),
  updated_at           timestamptz  not null default now(),
  constraint pk_work_product primary key (id),
  constraint uq_work_product__version unique (project_id, type, version),
  constraint fk_work_product__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_work_product__document_upload foreign key (document_upload_id) references document_upload (id) on delete set null,
  constraint fk_work_product__approved_by foreign key (approved_by_user_id) references app_user (id) on delete set null,
  constraint fk_work_product__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete set null,
  constraint ck_work_product__type check (type in (
    'STATEMENT_OF_WORK','PROJECT_PLAN','PROGRESS_STATUS_RECORD','MEETING_RECORD','CHANGE_REQUEST',
    'CORRECTION_REGISTER','ACCEPTANCE_RECORD','PROJECT_REPOSITORY','REPOSITORY_BACKUP','REQUIREMENTS_SPEC',
    'TRACEABILITY_RECORD','SOFTWARE_DESIGN','TEST_CASES_PROCEDURES','SOFTWARE_COMPONENT','SOFTWARE',
    'TEST_REPORT','PRODUCT_OPERATION_GUIDE','SOFTWARE_USER_DOC','SOFTWARE_CONFIGURATION','MAINTENANCE_DOC',
    'VERIFICATION_RESULTS','VALIDATION_RESULTS')),
  constraint ck_work_product__status check (status in ('NONE','DRAFT','SUBMITTED','APPROVED','REJECTED')),
  constraint ck_work_product__pm_activity check (pm_activity is null or pm_activity in ('PM_1','PM_2','PM_3','PM_4')),
  constraint ck_work_product__si_activity check (si_activity is null or si_activity in ('SI_1','SI_2','SI_3','SI_4','SI_5','SI_6')),
  constraint ck_work_product__activity check (pm_activity is not null or si_activity is not null),
  constraint ck_work_product__approved check ((status = 'APPROVED') = (approved_at is not null)),
  constraint ck_work_product__source_kind check (source_kind in ('TOOL','DOCUMENT','MANUAL'))
);

create unique index uq_work_product__current on work_product (project_id, type) where is_current;
create unique index uq_work_product__source on work_product (tool_connection_id, external_id)
  where tool_connection_id is not null and external_id is not null;
create index ix_work_product__project_status on work_product (project_id, status) where is_current;
create index ix_work_product__title_trgm on work_product using gin (title gin_trgm_ops);

create table requirement (
  id                  uuid         not null default gen_random_uuid(),
  project_id          uuid         not null,
  code                varchar(64),
  title               varchar(500) not null,
  body                text,
  priority            varchar(40)  not null default 'SHOULD',
  status              varchar(40)  not null default 'DEFINED',
  work_product_id     uuid,
  document_upload_id  uuid,
  assignee            varchar(200),
  source_created_at   timestamptz,
  source_updated_at   timestamptz,
  tool_connection_id  uuid,
  external_id         varchar(255),
  external_url        text,
  source_kind         varchar(40)  not null default 'MANUAL',
  created_at          timestamptz  not null default now(),
  updated_at          timestamptz  not null default now(),
  constraint pk_requirement primary key (id),
  constraint fk_requirement__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_requirement__work_product foreign key (work_product_id) references work_product (id) on delete set null,
  constraint fk_requirement__document_upload foreign key (document_upload_id) references document_upload (id) on delete set null,
  constraint fk_requirement__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete set null,
  constraint ck_requirement__priority check (priority in ('MUST','SHOULD','COULD','WONT')),
  constraint ck_requirement__status check (status in ('DEFINED','DESIGNED','IMPLEMENTED','VERIFIED','ACCEPTED','REJECTED')),
  constraint ck_requirement__source_kind check (source_kind in ('TOOL','DOCUMENT','MANUAL'))
);

create unique index uq_requirement__source on requirement (tool_connection_id, external_id)
  where tool_connection_id is not null and external_id is not null;
create unique index uq_requirement__code on requirement (project_id, code) where code is not null;
create index ix_requirement__project_status on requirement (project_id, status);
create index ix_requirement__title_trgm on requirement using gin (title gin_trgm_ops);
create index ix_requirement__work_product on requirement (work_product_id);

create table issue (
  id                  uuid         not null default gen_random_uuid(),
  project_id          uuid         not null,
  issue_key           varchar(64),
  title               varchar(500) not null,
  body                text,
  status              varchar(40)  not null default 'OPEN',
  severity            varchar(40)  not null default 'MAJOR',
  assignee            varchar(200),
  source_created_at   timestamptz,
  source_updated_at   timestamptz,
  resolved_at         timestamptz,
  tool_connection_id  uuid,
  external_id         varchar(255),
  external_url        text,
  source_kind         varchar(40)  not null default 'MANUAL',
  created_at          timestamptz  not null default now(),
  updated_at          timestamptz  not null default now(),
  constraint pk_issue primary key (id),
  constraint fk_issue__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_issue__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete set null,
  constraint ck_issue__status check (status in ('OPEN','IN_PROGRESS','RESOLVED','CLOSED')),
  constraint ck_issue__severity check (severity in ('BLOCKER','CRITICAL','MAJOR','MINOR','TRIVIAL')),
  constraint ck_issue__resolved check (status in ('RESOLVED','CLOSED') or resolved_at is null),
  constraint ck_issue__source_kind check (source_kind in ('TOOL','DOCUMENT','MANUAL'))
);

create unique index uq_issue__source on issue (tool_connection_id, external_id)
  where tool_connection_id is not null and external_id is not null;
create index ix_issue__project_status on issue (project_id, status);
create index ix_issue__key on issue (project_id, issue_key);
create index ix_issue__title_trgm on issue using gin (title gin_trgm_ops);

create table risk (
  id                  uuid         not null default gen_random_uuid(),
  project_id          uuid         not null,
  title               varchar(500) not null,
  body                text,
  probability         varchar(40)  not null default 'MEDIUM',
  impact              varchar(40)  not null default 'MEDIUM',
  severity            varchar(40)  not null,
  mitigation          text,
  owner               varchar(200),
  status              varchar(40)  not null default 'OPEN',
  identified_at       date,
  closed_at           timestamptz,
  tool_connection_id  uuid,
  external_id         varchar(255),
  external_url        text,
  source_kind         varchar(40)  not null default 'MANUAL',
  created_at          timestamptz  not null default now(),
  updated_at          timestamptz  not null default now(),
  constraint pk_risk primary key (id),
  constraint fk_risk__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_risk__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete set null,
  constraint ck_risk__probability check (probability in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint ck_risk__impact check (impact in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint ck_risk__severity check (severity in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint ck_risk__status check (status in ('OPEN','MITIGATING','CLOSED')),
  constraint ck_risk__source_kind check (source_kind in ('TOOL','DOCUMENT','MANUAL'))
);

create unique index uq_risk__source on risk (tool_connection_id, external_id)
  where tool_connection_id is not null and external_id is not null;
create index ix_risk__project_status_severity on risk (project_id, status, severity);

create table code_change (
  id                  uuid         not null default gen_random_uuid(),
  project_id          uuid         not null,
  kind                varchar(40)  not null,
  title               varchar(500) not null,
  ref_name            varchar(300),
  state               varchar(40)  not null,
  author              varchar(200),
  occurred_at         timestamptz  not null,
  work_product_id     uuid,
  tool_connection_id  uuid,
  external_id         varchar(255),
  external_url        text,
  source_kind         varchar(40)  not null default 'MANUAL',
  created_at          timestamptz  not null default now(),
  updated_at          timestamptz  not null default now(),
  constraint pk_code_change primary key (id),
  constraint fk_code_change__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_code_change__work_product foreign key (work_product_id) references work_product (id) on delete set null,
  constraint fk_code_change__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete set null,
  constraint ck_code_change__kind check (kind in ('COMMIT','MERGE_REQUEST','PIPELINE','RELEASE','TAG')),
  constraint ck_code_change__state check (state in ('OPENED','MERGED','CLOSED','SUCCESS','FAILED','CANCELED','CREATED')),
  constraint ck_code_change__source_kind check (source_kind in ('TOOL','DOCUMENT','MANUAL'))
);

create unique index uq_code_change__source on code_change (tool_connection_id, external_id)
  where tool_connection_id is not null and external_id is not null;
create index ix_code_change__project_kind_time on code_change (project_id, kind, occurred_at desc);
create index ix_code_change__work_product on code_change (work_product_id);

create table trace_link (
  id                  uuid        not null default gen_random_uuid(),
  project_id          uuid        not null,
  from_type           varchar(40) not null,
  from_id             uuid        not null,
  to_type             varchar(40) not null,
  to_id               uuid        not null,
  link_kind           varchar(40) not null,
  origin              varchar(40) not null default 'AUTO',
  status              varchar(40) not null default 'ACTIVE',
  created_by_user_id  uuid,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint pk_trace_link primary key (id),
  constraint uq_trace_link__edge unique (from_type, from_id, to_type, to_id, link_kind),
  constraint fk_trace_link__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_trace_link__created_by foreign key (created_by_user_id) references app_user (id) on delete set null,
  constraint ck_trace_link__from_type check (from_type in ('REQUIREMENT','ISSUE','WORK_PRODUCT','RISK','CODE_CHANGE','CHANGE_REQUEST','CORRECTION_ACTION')),
  constraint ck_trace_link__to_type check (to_type in ('REQUIREMENT','ISSUE','WORK_PRODUCT','RISK','CODE_CHANGE','CHANGE_REQUEST','CORRECTION_ACTION')),
  constraint ck_trace_link__link_kind check (link_kind in ('DESIGNS','IMPLEMENTS','TESTS','DELIVERS')),
  constraint ck_trace_link__origin check (origin in ('AUTO','MANUAL')),
  constraint ck_trace_link__status check (status in ('ACTIVE','BROKEN')),
  constraint ck_trace_link__self check (not (from_type = to_type and from_id = to_id))
);

create index ix_trace_link__to on trace_link (to_type, to_id, link_kind);
create index ix_trace_link__project_status on trace_link (project_id, status);

create table change_request (
  id                    uuid         not null default gen_random_uuid(),
  project_id            uuid         not null,
  code                  varchar(64)  not null,
  title                 varchar(500) not null,
  reason                text         not null,
  impact_summary        text,
  status                varchar(40)  not null default 'REQUESTED',
  requested_by_user_id  uuid,
  decided_by_user_id    uuid,
  requested_at          timestamptz  not null default now(),
  decided_at            timestamptz,
  applied_at            timestamptz,
  created_at            timestamptz  not null default now(),
  updated_at            timestamptz  not null default now(),
  constraint pk_change_request primary key (id),
  constraint uq_change_request__code unique (project_id, code),
  constraint fk_change_request__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_change_request__requested_by foreign key (requested_by_user_id) references app_user (id) on delete set null,
  constraint fk_change_request__decided_by foreign key (decided_by_user_id) references app_user (id) on delete set null,
  constraint ck_change_request__status check (status in ('REQUESTED','REVIEWING','APPROVED','REJECTED','APPLIED'))
);

create index ix_change_request__project_status on change_request (project_id, status);

create table correction_action (
  id                       uuid        not null default gen_random_uuid(),
  project_id               uuid        not null,
  code                     varchar(64) not null,
  finding                  text        not null,
  action                   text,
  owner                    varchar(200),
  due_date                 date        not null,
  status                   varchar(40) not null default 'OPEN',
  source_work_product_id   uuid,
  done_at                  timestamptz,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  constraint pk_correction_action primary key (id),
  constraint uq_correction_action__code unique (project_id, code),
  constraint fk_correction_action__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_correction_action__work_product foreign key (source_work_product_id) references work_product (id) on delete set null,
  constraint ck_correction_action__status check (status in ('OPEN','DONE','OVERDUE'))
);

create index ix_correction_action__project_status_due on correction_action (project_id, status, due_date);

create table progress_record (
  id                  uuid          not null default gen_random_uuid(),
  project_id          uuid          not null,
  period_start        date          not null,
  period_end          date          not null,
  planned_pct         numeric(5,2)  not null default 0,
  actual_pct          numeric(5,2)  not null default 0,
  summary             text,
  tool_connection_id  uuid,
  external_id         varchar(255),
  external_url        text,
  source_kind         varchar(40)   not null default 'MANUAL',
  created_at          timestamptz   not null default now(),
  updated_at          timestamptz   not null default now(),
  constraint pk_progress_record primary key (id),
  constraint uq_progress_record__period unique (project_id, period_start, period_end),
  constraint fk_progress_record__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_progress_record__tool_connection foreign key (tool_connection_id) references tool_connection (id) on delete set null,
  constraint ck_progress_record__period check (period_start <= period_end),
  constraint ck_progress_record__planned check (planned_pct >= 0 and planned_pct <= 100),
  constraint ck_progress_record__actual check (actual_pct >= 0 and actual_pct <= 100),
  constraint ck_progress_record__source_kind check (source_kind in ('TOOL','DOCUMENT','MANUAL'))
);

create unique index uq_progress_record__source on progress_record (tool_connection_id, external_id)
  where tool_connection_id is not null and external_id is not null;
create index ix_progress_record__project_period on progress_record (project_id, period_end desc);

create table meeting_record (
  id               uuid         not null default gen_random_uuid(),
  project_id       uuid         not null,
  title            varchar(500) not null,
  held_at          timestamptz  not null,
  attendees        text,
  minutes          text,
  work_product_id  uuid,
  created_at       timestamptz  not null default now(),
  updated_at       timestamptz  not null default now(),
  constraint pk_meeting_record primary key (id),
  constraint uq_meeting_record__held unique (project_id, held_at, title),
  constraint fk_meeting_record__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_meeting_record__work_product foreign key (work_product_id) references work_product (id) on delete set null
);

create index ix_meeting_record__project_held on meeting_record (project_id, held_at desc);

create table acceptance_record (
  id                    uuid        not null default gen_random_uuid(),
  project_id            uuid        not null,
  accepted_by_user_id   uuid        not null,
  accepted_at           timestamptz not null,
  conditions            text,
  work_product_id       uuid,
  status                varchar(40) not null default 'ISSUED',
  voided_at             timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  constraint pk_acceptance_record primary key (id),
  constraint fk_acceptance_record__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_acceptance_record__accepted_by foreign key (accepted_by_user_id) references app_user (id) on delete restrict,
  constraint fk_acceptance_record__work_product foreign key (work_product_id) references work_product (id) on delete set null,
  constraint ck_acceptance_record__status check (status in ('ISSUED','VOIDED'))
);

create unique index uq_acceptance_record__issued on acceptance_record (project_id) where status = 'ISSUED';

create table entity_history (
  id           uuid         not null default gen_random_uuid(),
  entity_type  varchar(40)  not null,
  entity_id    uuid         not null,
  project_id   uuid,
  field        varchar(60)  not null,
  from_value   text,
  to_value     text,
  changed_at   timestamptz  not null default now(),
  actor        varchar(120) not null,
  created_at   timestamptz  not null default now(),
  constraint pk_entity_history primary key (id),
  constraint fk_entity_history__project foreign key (project_id) references project (id) on delete cascade,
  constraint ck_entity_history__entity_type check (entity_type in (
    'PROJECT','PROJECT_ASSIGNMENT','ORGANIZATION','APP_USER','TOOL_CONNECTION','REQUIREMENT','ISSUE',
    'WORK_PRODUCT','RISK','CODE_CHANGE','TRACE_LINK','CHANGE_REQUEST','CORRECTION_ACTION',
    'PROGRESS_RECORD','ACCEPTANCE_RECORD','DOCUMENT_UPLOAD'))
);

create index ix_entity_history__entity on entity_history (entity_type, entity_id, changed_at desc);
create index ix_entity_history__project on entity_history (project_id, changed_at desc);

-- ============================================================
-- 5. INS — 시맨틱 카탈로그 · 대시보드
-- ============================================================

create table semantic_measure (
  id                  uuid         not null default gen_random_uuid(),
  key                 varchar(64)  not null,
  label               varchar(200) not null,
  description         text         not null,
  base_table          varchar(60)  not null,
  join_clause         text,
  row_filter          text,
  value_expr          text         not null,
  value_type          varchar(40)  not null,
  unit                varchar(10),
  allowed_dimensions  text[]       not null default '{}',
  allowed_filters     text[]       not null default '{}',
  default_dimension   varchar(64),
  status              varchar(40)  not null default 'ACTIVE',
  created_at          timestamptz  not null default now(),
  updated_at          timestamptz  not null default now(),
  constraint pk_semantic_measure primary key (id),
  constraint uq_semantic_measure__key unique (key),
  constraint ck_semantic_measure__base_table check (base_table in (
    'requirement','issue','work_product','risk','code_change','change_request','correction_action','progress_record')),
  constraint ck_semantic_measure__value_type check (value_type in ('COUNT','RATE_PCT','DAYS','PCT_POINT')),
  constraint ck_semantic_measure__status check (status in ('ACTIVE','DEPRECATED'))
);

create table semantic_dimension (
  id             uuid         not null default gen_random_uuid(),
  key            varchar(64)  not null,
  label          varchar(200) not null,
  description    text         not null,
  select_expr    text         not null,
  label_expr     text,
  requires_join  text,
  value_type     varchar(40)  not null,
  status         varchar(40)  not null default 'ACTIVE',
  created_at     timestamptz  not null default now(),
  updated_at     timestamptz  not null default now(),
  constraint pk_semantic_dimension primary key (id),
  constraint uq_semantic_dimension__key unique (key),
  constraint ck_semantic_dimension__value_type check (value_type in ('CATEGORY','TIME')),
  constraint ck_semantic_dimension__status check (status in ('ACTIVE','DEPRECATED'))
);

create table semantic_filter (
  id           uuid         not null default gen_random_uuid(),
  key          varchar(64)  not null,
  field        varchar(64)  not null,
  op           varchar(40)  not null,
  label        varchar(200) not null,
  description  text         not null,
  column_expr  text         not null,
  value_type   varchar(40)  not null,
  enum_values  text[],
  status       varchar(40)  not null default 'ACTIVE',
  created_at   timestamptz  not null default now(),
  updated_at   timestamptz  not null default now(),
  constraint pk_semantic_filter primary key (id),
  constraint uq_semantic_filter__key unique (key),
  constraint uq_semantic_filter__field_op unique (field, op),
  constraint ck_semantic_filter__op check (op in ('IN','EQ','BETWEEN','IN_MONTH','LAST_N_DAYS','GTE','LTE')),
  constraint ck_semantic_filter__value_type check (value_type in ('ENUM_LIST','UUID_LIST','DATE_RANGE','MONTH_TOKEN','INT')),
  constraint ck_semantic_filter__status check (status in ('ACTIVE','DEPRECATED'))
);

create table dashboard (
  id             uuid         not null default gen_random_uuid(),
  project_id     uuid,
  owner_user_id  uuid         not null,
  name           varchar(200) not null,
  layout_json    jsonb        not null default '{"version":1,"lg":[],"md":[],"sm":[]}'::jsonb,
  is_default     boolean      not null default false,
  status         varchar(40)  not null default 'ACTIVE',
  created_at     timestamptz  not null default now(),
  updated_at     timestamptz  not null default now(),
  constraint pk_dashboard primary key (id),
  constraint fk_dashboard__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_dashboard__owner foreign key (owner_user_id) references app_user (id) on delete cascade,
  constraint ck_dashboard__status check (status in ('ACTIVE','DELETED'))
);

create unique index uq_dashboard__name
  on dashboard (owner_user_id, (coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)), name)
  where status = 'ACTIVE';
create unique index uq_dashboard__default on dashboard (project_id) where is_default and status = 'ACTIVE';

create table widget (
  id                  uuid         not null default gen_random_uuid(),
  dashboard_id        uuid         not null,
  template            varchar(40)  not null,
  title               varchar(200) not null,
  spec_json           jsonb        not null,
  status              varchar(40)  not null default 'ACTIVE',
  created_by_user_id  uuid         not null,
  created_at          timestamptz  not null default now(),
  updated_at          timestamptz  not null default now(),
  constraint pk_widget primary key (id),
  constraint fk_widget__dashboard foreign key (dashboard_id) references dashboard (id) on delete cascade,
  constraint fk_widget__created_by foreign key (created_by_user_id) references app_user (id) on delete restrict,
  constraint ck_widget__template check (template in (
    'STAT_CARD','BAR_CHART','LINE_CHART','PIE_CHART','PROGRESS_LIST','DATA_TABLE','CHECKLIST','GANTT_SUMMARY')),
  constraint ck_widget__status check (status in ('ACTIVE','DELETED'))
);

create index ix_widget__dashboard on widget (dashboard_id) where status = 'ACTIVE';

-- ============================================================
-- 6. KNW — 청크 · 정형화 · Q&A
-- ============================================================

create table doc_chunk (
  id               uuid         not null default gen_random_uuid(),
  project_id       uuid         not null,
  source_type      varchar(40)  not null,
  source_id        uuid         not null,
  chunk_index      integer      not null,
  content          text         not null,
  embedding        vector(1024) not null,
  embedding_model  varchar(60)  not null default 'bge-m3',
  token_count      integer,
  source_title     varchar(500) not null,
  source_uri       text         not null,
  content_hash     char(64)     not null,
  meta_json        jsonb        not null default '{}'::jsonb,
  indexed_at       timestamptz  not null default now(),
  created_at       timestamptz  not null default now(),
  content_tsv      tsvector generated always as (to_tsvector('simple', coalesce(source_title, '') || ' ' || content)) stored,
  constraint pk_doc_chunk primary key (id),
  constraint uq_doc_chunk__source unique (source_type, source_id, chunk_index),
  constraint fk_doc_chunk__project foreign key (project_id) references project (id) on delete cascade,
  constraint ck_doc_chunk__source_type check (source_type in (
    'WORK_PRODUCT','REQUIREMENT','ISSUE','RISK','CHANGE_REQUEST','CORRECTION_ACTION',
    'MEETING_RECORD','PROGRESS_RECORD','DOCUMENT_UPLOAD')),
  constraint ck_doc_chunk__index check (chunk_index >= 0),
  constraint ck_doc_chunk__content check (length(btrim(content)) > 0)
);

create index ix_doc_chunk__embedding_hnsw on doc_chunk using hnsw (embedding vector_cosine_ops) with (m = 16, ef_construction = 64);
create index ix_doc_chunk__tsv on doc_chunk using gin (content_tsv);
create index ix_doc_chunk__content_trgm on doc_chunk using gin (content gin_trgm_ops);
create index ix_doc_chunk__project on doc_chunk (project_id);
create index ix_doc_chunk__source_lookup on doc_chunk (source_type, source_id);

create table structuring_draft (
  id                    uuid         not null default gen_random_uuid(),
  document_upload_id    uuid         not null,
  model                 varchar(60)  not null default 'deepseek-v4-pro:cloud',
  draft_json            jsonb        not null,
  proposed_type         varchar(40),
  type_rejected         boolean      not null default false,
  status                varchar(40)  not null default 'PROPOSED',
  confirmed_by_user_id  uuid,
  confirmed_at          timestamptz,
  work_product_id       uuid,
  created_at            timestamptz  not null default now(),
  updated_at            timestamptz  not null default now(),
  constraint pk_structuring_draft primary key (id),
  constraint uq_structuring_draft__upload unique (document_upload_id),
  constraint fk_structuring_draft__document_upload foreign key (document_upload_id) references document_upload (id) on delete cascade,
  constraint fk_structuring_draft__confirmed_by foreign key (confirmed_by_user_id) references app_user (id) on delete set null,
  constraint fk_structuring_draft__work_product foreign key (work_product_id) references work_product (id) on delete set null,
  constraint ck_structuring_draft__proposed_type check (proposed_type is null or proposed_type in (
    'STATEMENT_OF_WORK','PROJECT_PLAN','PROGRESS_STATUS_RECORD','MEETING_RECORD','CHANGE_REQUEST',
    'CORRECTION_REGISTER','ACCEPTANCE_RECORD','PROJECT_REPOSITORY','REPOSITORY_BACKUP','REQUIREMENTS_SPEC',
    'TRACEABILITY_RECORD','SOFTWARE_DESIGN','TEST_CASES_PROCEDURES','SOFTWARE_COMPONENT','SOFTWARE',
    'TEST_REPORT','PRODUCT_OPERATION_GUIDE','SOFTWARE_USER_DOC','SOFTWARE_CONFIGURATION','MAINTENANCE_DOC',
    'VERIFICATION_RESULTS','VALIDATION_RESULTS')),
  constraint ck_structuring_draft__status check (status in ('PROPOSED','CONFIRMED','REJECTED','MANUAL_OVERRIDE'))
);

create table conversation (
  id               uuid         not null default gen_random_uuid(),
  user_id          uuid         not null,
  title            varchar(200) not null default '새 대화',
  project_scope    uuid[]       not null default '{}',
  pinned           boolean      not null default false,
  status           varchar(40)  not null default 'ACTIVE',
  last_message_at  timestamptz,
  created_at       timestamptz  not null default now(),
  updated_at       timestamptz  not null default now(),
  constraint pk_conversation primary key (id),
  constraint fk_conversation__app_user foreign key (user_id) references app_user (id) on delete cascade,
  constraint ck_conversation__status check (status in ('ACTIVE','DELETED'))
);

create index ix_conversation__user on conversation (user_id, pinned desc, last_message_at desc) where status = 'ACTIVE';

create table message (
  id               uuid        not null default gen_random_uuid(),
  conversation_id  uuid        not null,
  seq              integer     not null,
  role             varchar(40) not null,
  content          text        not null,
  status           varchar(40) not null default 'COMPLETE',
  route_type       varchar(40),
  rewritten_query  text,
  feedback         varchar(40),
  latency_ms       integer,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint pk_message primary key (id),
  constraint uq_message__seq unique (conversation_id, seq),
  constraint fk_message__conversation foreign key (conversation_id) references conversation (id) on delete cascade,
  constraint ck_message__role check (role in ('USER','ASSISTANT')),
  constraint ck_message__status check (status in ('STREAMING','COMPLETE','ABORTED')),
  constraint ck_message__route_type check (route_type is null or route_type in ('DOCUMENT','AGGREGATE','MIXED')),
  constraint ck_message__feedback check (feedback is null or feedback in ('UP','DOWN'))
);

create table message_source (
  id            uuid         not null default gen_random_uuid(),
  message_id    uuid         not null,
  footnote_no   integer      not null,
  doc_chunk_id  uuid,
  source_type   varchar(40)  not null,
  source_title  varchar(500) not null,
  snippet       text         not null,
  external_url  text         not null,
  page_no       integer,
  created_at    timestamptz  not null default now(),
  constraint pk_message_source primary key (id),
  constraint uq_message_source__footnote unique (message_id, footnote_no),
  constraint fk_message_source__message foreign key (message_id) references message (id) on delete cascade,
  constraint fk_message_source__doc_chunk foreign key (doc_chunk_id) references doc_chunk (id) on delete set null,
  constraint ck_message_source__footnote check (footnote_no >= 1),
  constraint ck_message_source__source_type check (source_type in (
    'WORK_PRODUCT','REQUIREMENT','ISSUE','RISK','CHANGE_REQUEST','CORRECTION_ACTION',
    'MEETING_RECORD','PROGRESS_RECORD','DOCUMENT_UPLOAD'))
);

create index ix_message_source__doc_chunk on message_source (doc_chunk_id);

-- ============================================================
-- 7. 시드 — semantic_measure 13행
-- ============================================================

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter, value_expr, value_type, unit, allowed_dimensions, allowed_filters, default_dimension) values
('requirement_fulfillment_rate', '요구사항 이행률',
 '요구사항 중 검증완료·인수완료 비율(%). "요구사항 이행률", "요구사항 완료율" 질문에 사용',
 'requirement', null, null,
 'round(100.0 * count(*) filter (where e.status in (''VERIFIED'',''ACCEPTED'')) / nullif(count(*), 0), 2)',
 'RATE_PCT', '%',
 '{project,contractor_org,requirement_priority,requirement_status,period_month}',
 '{project_id__in,requirement_priority__in,requirement_status__in,contractor_org_id__in,period__between,period__in_month,period__last_n_days}',
 'project'),

('requirement_test_trace_rate', '요구사항→시험 추적률',
 '시험(TESTS) 추적 링크가 연결된 요구사항의 비율(%). "추적률", "테스트 커버리지" 질문에 사용',
 'requirement',
 'left join trace_link tl on tl.to_type = ''REQUIREMENT'' and tl.to_id = e.id and tl.link_kind = ''TESTS'' and tl.status = ''ACTIVE''',
 null,
 'round(100.0 * count(distinct e.id) filter (where tl.id is not null) / nullif(count(distinct e.id), 0), 2)',
 'RATE_PCT', '%',
 '{project,contractor_org,requirement_priority,requirement_status}',
 '{project_id__in,requirement_priority__in,requirement_status__in,period__between}',
 'project'),

('work_product_approval_rate', '산출물 승인률',
 '적용 대상 산출물 중 승인 완료 비율(%). ISO 29110 산출물 22종 기준',
 'work_product', null, 'e.is_current and e.applicable',
 'round(100.0 * count(*) filter (where e.status = ''APPROVED'') / nullif(count(*), 0), 2)',
 'RATE_PCT', '%',
 '{project,work_product_type,iso_activity,work_product_status}',
 '{project_id__in,work_product_type__in,work_product_status__in,iso_activity__in}',
 'work_product_type'),

('work_product_missing_count', '미제출 산출물 수',
 '적용 대상이지만 아직 제출되지 않은(상태 NONE) 산출물 건수',
 'work_product', null, 'e.is_current and e.applicable',
 'count(*) filter (where e.status = ''NONE'')',
 'COUNT', '건',
 '{project,work_product_type,iso_activity}',
 '{project_id__in,work_product_type__in,iso_activity__in}',
 'work_product_type'),

('issue_resolution_rate', '이슈 처리율',
 '이슈 중 해결·종료 비율(%). "이슈 처리율" 질문에 사용',
 'issue', null, null,
 'round(100.0 * count(*) filter (where e.status in (''RESOLVED'',''CLOSED'')) / nullif(count(*), 0), 2)',
 'RATE_PCT', '%',
 '{project,contractor_org,issue_severity,issue_status,assignee,period_month,period_week}',
 '{project_id__in,issue_status__in,issue_severity__in,contractor_org_id__in,period__between,period__in_month,period__last_n_days}',
 'project'),

('issue_avg_resolution_days', '이슈 평균 처리일',
 '이슈 생성부터 해결까지 걸린 평균 일수',
 'issue', null, 'e.resolved_at is not null and e.source_created_at is not null',
 'round(avg(extract(epoch from (e.resolved_at - e.source_created_at)) / 86400.0)::numeric, 2)',
 'DAYS', '일',
 '{project,contractor_org,issue_severity,assignee,period_month}',
 '{project_id__in,issue_severity__in,contractor_org_id__in,period__between,period__in_month}',
 'project'),

('open_issue_count', '열린 이슈 수',
 '아직 열려 있거나 진행 중인 이슈 건수',
 'issue', null, 'e.status in (''OPEN'',''IN_PROGRESS'')',
 'count(*)',
 'COUNT', '건',
 '{project,contractor_org,issue_severity,assignee}',
 '{project_id__in,issue_severity__in,contractor_org_id__in,period__last_n_days}',
 'issue_severity'),

('open_risk_count', '열린 리스크 수',
 '종료되지 않은 리스크 건수. 심각도별로 나눠 볼 수 있다',
 'risk', null, 'e.status <> ''CLOSED''',
 'count(*)',
 'COUNT', '건',
 '{project,risk_severity,risk_status,period_month}',
 '{project_id__in,risk_severity__in,risk_status__in,period__between}',
 'risk_severity'),

('correction_overdue_count', '시정조치 지연 건수',
 '기한이 지났는데 완료되지 않은 시정조치 건수',
 'correction_action', null, 'e.status = ''OVERDUE'' or (e.status = ''OPEN'' and e.due_date < current_date)',
 'count(*)',
 'COUNT', '건',
 '{project,correction_status,period_month}',
 '{project_id__in,correction_status__in,period__between,period__last_n_days}',
 'project'),

('change_request_count', '변경요청 처리 현황',
 '변경요청 건수. 상태별로 나눠 처리 현황을 본다',
 'change_request', null, null,
 'count(*)',
 'COUNT', '건',
 '{project,change_request_status,period_month}',
 '{project_id__in,change_request_status__in,period__between,period__in_month}',
 'change_request_status'),

('code_activity_count', '커밋·MR 활동량',
 '커밋·머지리퀘스트 건수. 개발 활동량 지표',
 'code_change', null, 'e.kind in (''COMMIT'',''MERGE_REQUEST'')',
 'count(*)',
 'COUNT', '건',
 '{project,contractor_org,code_change_kind,period_month,period_week,assignee}',
 '{project_id__in,code_change_kind__in,contractor_org_id__in,period__between,period__in_month,period__last_n_days}',
 'period_month'),

('test_pass_rate', '시험 통과율',
 'CI 파이프라인 성공 비율(%). "시험 통과율", "빌드 성공률" 질문에 사용',
 'code_change', null, 'e.kind = ''PIPELINE''',
 'round(100.0 * count(*) filter (where e.state = ''SUCCESS'') / nullif(count(*), 0), 2)',
 'RATE_PCT', '%',
 '{project,contractor_org,period_month,period_week}',
 '{project_id__in,contractor_org_id__in,period__between,period__in_month,period__last_n_days}',
 'period_month'),

('schedule_variance_pct', '일정 진척(계획 대비)',
 '실적 진척률에서 계획 진척률을 뺀 값(%p). 음수면 지연',
 'progress_record', null, null,
 'round(avg(e.actual_pct - e.planned_pct), 2)',
 'PCT_POINT', '%p',
 '{project,period_month,period_week}',
 '{project_id__in,period__between,period__in_month}',
 'period_month');

-- ============================================================
-- 8. 시드 — semantic_dimension 17행
-- ============================================================

insert into semantic_dimension (key, label, description, select_expr, label_expr, requires_join, value_type) values
('project', '프로젝트', '프로젝트 단위로 나눈다', 'e.project_id::text', 'p.name', 'join project p on p.id = e.project_id', 'CATEGORY'),
('contractor_org', '용역사', '데이터를 수집한 연결의 소유 용역사 단위로 나눈다. 연결 없는 행은 미지정',
 'coalesce(tc.contractor_org_id::text, ''UNASSIGNED'')', 'coalesce(o.name, ''미지정'')',
 'left join tool_connection tc on tc.id = e.tool_connection_id left join organization o on o.id = tc.contractor_org_id', 'CATEGORY'),
('work_product_type', '산출물 유형', 'ISO 29110 산출물 22종 유형별로 나눈다', 'e.type', null, null, 'CATEGORY'),
('work_product_status', '산출물 상태', '산출물 제출·승인 상태별로 나눈다', 'e.status', null, null, 'CATEGORY'),
('requirement_status', '요구사항 상태', '요구사항 진행 상태별로 나눈다', 'e.status', null, null, 'CATEGORY'),
('requirement_priority', '요구사항 우선순위', 'MoSCoW 우선순위별로 나눈다', 'e.priority', null, null, 'CATEGORY'),
('issue_status', '이슈 상태', '이슈 처리 상태별로 나눈다', 'e.status', null, null, 'CATEGORY'),
('issue_severity', '이슈 심각도', '이슈 심각도별로 나눈다', 'e.severity', null, null, 'CATEGORY'),
('risk_severity', '리스크 심각도', '리스크 심각도별로 나눈다', 'e.severity', null, null, 'CATEGORY'),
('risk_status', '리스크 상태', '리스크 대응 상태별로 나눈다', 'e.status', null, null, 'CATEGORY'),
('iso_activity', 'ISO 활동', 'ISO 29110 PM·SI 활동 단계별로 나눈다', 'coalesce(e.pm_activity, e.si_activity)', null, null, 'CATEGORY'),
('change_request_status', '변경요청 상태', '변경요청 처리 상태별로 나눈다', 'e.status', null, null, 'CATEGORY'),
('correction_status', '시정조치 상태', '시정조치 처리 상태별로 나눈다', 'e.status', null, null, 'CATEGORY'),
('code_change_kind', '형상 개체 종류', '커밋·MR·파이프라인 등 형상 개체 종류별로 나눈다', 'e.kind', null, null, 'CATEGORY'),
('assignee', '담당자', '담당자·작성자 표시명별로 나눈다', 'coalesce(e.assignee, ''미지정'')', null, null, 'CATEGORY'),
('period_month', '월', '월 단위 시계열로 나눈다', 'to_char(date_trunc(''month'', <TIME_COL>), ''YYYY-MM'')', null, null, 'TIME'),
('period_week', '주', '주 단위 시계열로 나눈다', 'to_char(date_trunc(''week'', <TIME_COL>), ''IYYY-"W"IW'')', null, null, 'TIME');

-- ============================================================
-- 9. 시드 — semantic_filter 17행
-- ============================================================

insert into semantic_filter (key, field, op, label, description, column_expr, value_type, enum_values) values
('project_id__in', 'project_id', 'IN', '프로젝트', '특정 프로젝트로 한정한다', 'e.project_id', 'UUID_LIST', null),
('contractor_org_id__in', 'contractor_org_id', 'IN', '용역사', '특정 용역사가 수집한 데이터로 한정한다', 'tc.contractor_org_id', 'UUID_LIST', null),
('work_product_type__in', 'work_product_type', 'IN', '산출물 유형', '특정 산출물 유형으로 한정한다', 'e.type', 'ENUM_LIST',
 '{STATEMENT_OF_WORK,PROJECT_PLAN,PROGRESS_STATUS_RECORD,MEETING_RECORD,CHANGE_REQUEST,CORRECTION_REGISTER,ACCEPTANCE_RECORD,PROJECT_REPOSITORY,REPOSITORY_BACKUP,REQUIREMENTS_SPEC,TRACEABILITY_RECORD,SOFTWARE_DESIGN,TEST_CASES_PROCEDURES,SOFTWARE_COMPONENT,SOFTWARE,TEST_REPORT,PRODUCT_OPERATION_GUIDE,SOFTWARE_USER_DOC,SOFTWARE_CONFIGURATION,MAINTENANCE_DOC,VERIFICATION_RESULTS,VALIDATION_RESULTS}'),
('work_product_status__in', 'work_product_status', 'IN', '산출물 상태', '특정 산출물 상태로 한정한다', 'e.status', 'ENUM_LIST',
 '{NONE,DRAFT,SUBMITTED,APPROVED,REJECTED}'),
('requirement_status__in', 'requirement_status', 'IN', '요구사항 상태', '특정 요구사항 상태로 한정한다', 'e.status', 'ENUM_LIST',
 '{DEFINED,DESIGNED,IMPLEMENTED,VERIFIED,ACCEPTED,REJECTED}'),
('requirement_priority__in', 'requirement_priority', 'IN', '요구사항 우선순위', '특정 MoSCoW 우선순위로 한정한다', 'e.priority', 'ENUM_LIST',
 '{MUST,SHOULD,COULD,WONT}'),
('issue_status__in', 'issue_status', 'IN', '이슈 상태', '특정 이슈 상태로 한정한다', 'e.status', 'ENUM_LIST',
 '{OPEN,IN_PROGRESS,RESOLVED,CLOSED}'),
('issue_severity__in', 'issue_severity', 'IN', '이슈 심각도', '특정 이슈 심각도로 한정한다', 'e.severity', 'ENUM_LIST',
 '{BLOCKER,CRITICAL,MAJOR,MINOR,TRIVIAL}'),
('risk_severity__in', 'risk_severity', 'IN', '리스크 심각도', '특정 리스크 심각도로 한정한다', 'e.severity', 'ENUM_LIST',
 '{LOW,MEDIUM,HIGH,CRITICAL}'),
('risk_status__in', 'risk_status', 'IN', '리스크 상태', '특정 리스크 상태로 한정한다', 'e.status', 'ENUM_LIST',
 '{OPEN,MITIGATING,CLOSED}'),
('change_request_status__in', 'change_request_status', 'IN', '변경요청 상태', '특정 변경요청 상태로 한정한다', 'e.status', 'ENUM_LIST',
 '{REQUESTED,REVIEWING,APPROVED,REJECTED,APPLIED}'),
('correction_status__in', 'correction_status', 'IN', '시정조치 상태', '특정 시정조치 상태로 한정한다', 'e.status', 'ENUM_LIST',
 '{OPEN,DONE,OVERDUE}'),
('code_change_kind__in', 'code_change_kind', 'IN', '형상 개체 종류', '커밋·MR·파이프라인 등 종류로 한정한다', 'e.kind', 'ENUM_LIST',
 '{COMMIT,MERGE_REQUEST,PIPELINE,RELEASE,TAG}'),
('iso_activity__in', 'iso_activity', 'IN', 'ISO 활동', '특정 ISO 29110 활동 단계로 한정한다', 'coalesce(e.pm_activity, e.si_activity)', 'ENUM_LIST',
 '{PM_1,PM_2,PM_3,PM_4,SI_1,SI_2,SI_3,SI_4,SI_5,SI_6}'),
('period__between', 'period', 'BETWEEN', '기간(구간)', '시작일과 종료일 사이로 한정한다', '<TIME_COL>', 'DATE_RANGE', null),
('period__in_month', 'period', 'IN_MONTH', '기간(월)', '특정 월(YYYY-MM 또는 current)로 한정한다', '<TIME_COL>', 'MONTH_TOKEN', null),
('period__last_n_days', 'period', 'LAST_N_DAYS', '기간(최근 N일)', '최근 N일로 한정한다', '<TIME_COL>', 'INT', null);

-- ============================================================
-- 10. 시드 — 기본 조직 · 계정 · 데모 프로젝트
-- ============================================================

insert into organization (id, name, type, business_no, status) values
('a0000000-0000-4000-8000-000000000001', 'AX-Link 운영본부', 'CLIENT',     null,             'ACTIVE'),
('a0000000-0000-4000-8000-000000000002', '한국디지털공사',   'CLIENT',     '123-45-67890',   'ACTIVE'),
('a0000000-0000-4000-8000-000000000003', '넥스트소프트',     'CONTRACTOR', '210-81-11223',   'ACTIVE');

insert into app_user (id, organization_id, email, name, password_hash, role, status) values
('b0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000001', 'admin@axlink.co.kr',
 '플랫폼 관리자', '$2y$10$iZc2Ri.WsQgbD20M68B/EuJqlTHhL1tvURkptR4oAJZvJkvdkSlUG', 'SUPER_ADMIN', 'ACTIVE'),
('b0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000002', 'client@axlink.co.kr',
 '발주사 담당자', '$2y$10$SvQwVA9vG4ToeaUdZsr2VOe8tIyxG0NmHp/BMgqkuBe6cnDj6svRy', 'CLIENT', 'ACTIVE'),
('b0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000003', 'contractor@axlink.co.kr',
 '용역사 PM', '$2y$10$CBuzzYfNRwjTyDAPTsZd4O99aNvHxsWgADRA8ws2wvzkYpYCBneT2', 'CONTRACTOR', 'ACTIVE');

insert into project (id, client_org_id, name, start_date, end_date, description, status, current_si_phase) values
('c0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
 '차세대 통합관제 시스템 구축', date '2026-03-02', date '2026-12-31',
 'ISO/IEC 29110 기반 SI 사업 관리 데모 프로젝트. 요구사항·산출물·이슈·형상 이력을 도구 연동으로 표준 적재한다.',
 'ACTIVE', 'SI_2');

insert into project_assignment (project_id, contractor_org_id, user_id, permissions_json, assigned_by_user_id) values
('c0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000003',
 'b0000000-0000-4000-8000-000000000003',
 '{"canConfigureIntegration":true,"canUploadDocument":true,"canReadDashboard":true}'::jsonb,
 'b0000000-0000-4000-8000-000000000002');

insert into work_product (project_id, type, pm_activity, si_activity)
select 'c0000000-0000-4000-8000-000000000001', t.type, t.pm_activity, t.si_activity
  from (values
    ('STATEMENT_OF_WORK',       'PM_1', null),
    ('PROJECT_PLAN',            'PM_1', null),
    ('PROGRESS_STATUS_RECORD',  'PM_2', null),
    ('MEETING_RECORD',          'PM_2', null),
    ('CHANGE_REQUEST',          'PM_2', null),
    ('CORRECTION_REGISTER',     'PM_3', null),
    ('ACCEPTANCE_RECORD',       'PM_4', null),
    ('PROJECT_REPOSITORY',      'PM_1', null),
    ('REPOSITORY_BACKUP',       'PM_2', null),
    ('VERIFICATION_RESULTS',    'PM_3', null),
    ('VALIDATION_RESULTS',      'PM_4', null),
    ('REQUIREMENTS_SPEC',       null,   'SI_2'),
    ('TRACEABILITY_RECORD',     null,   'SI_2'),
    ('SOFTWARE_DESIGN',         null,   'SI_3'),
    ('TEST_CASES_PROCEDURES',   null,   'SI_3'),
    ('SOFTWARE_COMPONENT',      null,   'SI_4'),
    ('SOFTWARE',                null,   'SI_5'),
    ('TEST_REPORT',             null,   'SI_5'),
    ('PRODUCT_OPERATION_GUIDE', null,   'SI_5'),
    ('SOFTWARE_USER_DOC',       null,   'SI_5'),
    ('SOFTWARE_CONFIGURATION',  null,   'SI_6'),
    ('MAINTENANCE_DOC',         null,   'SI_6')
  ) as t (type, pm_activity, si_activity);

insert into dashboard (project_id, owner_user_id, name, is_default) values
('c0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000002', '사업 현황', true);

-- ============================================================
-- 11. entity_history append-only 권한 회수 (INV-16)
-- ============================================================

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'axlink_app') then
    execute 'revoke update, delete on entity_history from axlink_app';
  end if;
end
$$;
