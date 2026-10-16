-- 공동 수급 1단계 (GH-138, ARC-029)
--
-- 사업에 참여하는 용역 업체를 따로 둔다. 대표사·참여사 구분은 표시용이고 권한이 없다.
-- 참여 업체는 사업의 업무 정보를 함께 보고, 도구 연결의 설정 변경·삭제는 그 연결을 만든
-- 업체(tool_connection.contractor_org_id)와 발주기관만 한다. 지우거나 다시 만드는 행은 없다.

create table project_participant (
  id                  uuid          not null default gen_random_uuid(),
  project_id          uuid          not null,
  organization_id     uuid          not null,
  role                varchar(20)   not null default 'PARTICIPANT',
  work_note           varchar(300),
  status              varchar(20)   not null default 'ACTIVE',
  created_by_user_id  uuid,
  removed_at          timestamptz,
  created_at          timestamptz   not null default now(),
  updated_at          timestamptz   not null default now(),
  constraint pk_project_participant primary key (id),
  constraint fk_project_participant__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_project_participant__organization foreign key (organization_id) references organization (id) on delete restrict,
  constraint fk_project_participant__created_by foreign key (created_by_user_id) references app_user (id) on delete set null,
  constraint ck_project_participant__role check (role in ('REPRESENTATIVE','PARTICIPANT')),
  constraint ck_project_participant__status check (status in ('ACTIVE','REMOVED')),
  constraint ck_project_participant__removed check ((status = 'REMOVED') = (removed_at is not null))
);

create unique index uq_project_participant__active on project_participant (project_id, organization_id)
  where status = 'ACTIVE';
-- 대표사는 사업에 하나(표시)
create unique index uq_project_participant__representative on project_participant (project_id)
  where status = 'ACTIVE' and role = 'REPRESENTATIVE';

-- 기존 사업 전환: 지금 할당돼 있는 용역사 조직을 참여 업체로 옮긴다. 사업 정보의 용역사 이름과
-- 조직 이름이 정확히 같을 때만 대표사로 둔다. 맞는 조직이 없으면 대표사를 정하지 않는다
insert into project_participant (project_id, organization_id, role)
select distinct a.project_id, a.contractor_org_id,
       case when o.name = p.contractor_name then 'REPRESENTATIVE' else 'PARTICIPANT' end
  from project_assignment a
  join organization o on o.id = a.contractor_org_id and o.type = 'CONTRACTOR'
  join project p on p.id = a.project_id
 where a.status = 'ACTIVE';

-- 업체를 지정한 초대. 비어 있으면 이 마이그레이션 전에 만든 초대다(새 업체 등록만 받는다)
alter table project_invite add column organization_id uuid;
alter table project_invite add constraint fk_project_invite__organization
  foreign key (organization_id) references organization (id) on delete restrict;

alter table entity_history drop constraint ck_entity_history__entity_type;
alter table entity_history add constraint ck_entity_history__entity_type check (entity_type in (
  'PROJECT','PROJECT_ASSIGNMENT','ORGANIZATION','APP_USER','TOOL_CONNECTION','REQUIREMENT','ISSUE',
  'WORK_PRODUCT','RISK','CODE_CHANGE','TRACE_LINK','CHANGE_REQUEST','CORRECTION_ACTION',
  'PROGRESS_RECORD','ACCEPTANCE_RECORD','DOCUMENT_UPLOAD','REQUIREMENT_BASELINE','PROJECT_PARTICIPANT'));
