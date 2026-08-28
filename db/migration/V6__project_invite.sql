-- 용역사 초대 링크: 발주사가 링크를 만들어 전달하면, 용역사가 직접 계정을 만들고
-- 해당 프로젝트에 자동 할당된다. 링크 하나로 여러 명이 가입할 수 있다.
create table project_invite (
  id                 uuid        not null default gen_random_uuid(),
  project_id         uuid        not null,
  contractor_org_id  uuid        not null,
  token_hash         char(64)    not null,
  permissions_json   jsonb       not null default '{"canConfigureIntegration":false,"canUploadDocument":false,"canReadDashboard":false}'::jsonb,
  expires_at         timestamptz not null,
  revoked_at         timestamptz,
  created_by_user_id uuid        not null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint pk_project_invite primary key (id),
  constraint uq_project_invite__token_hash unique (token_hash),
  constraint fk_project_invite__project foreign key (project_id) references project (id) on delete cascade,
  constraint fk_project_invite__organization foreign key (contractor_org_id) references organization (id) on delete restrict,
  constraint fk_project_invite__created_by foreign key (created_by_user_id) references app_user (id) on delete restrict
);

create index ix_project_invite__project on project_invite (project_id);
