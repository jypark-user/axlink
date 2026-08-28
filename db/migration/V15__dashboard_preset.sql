-- 꾸민 대시보드 구성을 이름 붙여 두고 다른 사업에서 다시 쓴다.
-- 위젯 명세와 자리만 담는다 — 값은 볼 때마다 그 사업 범위로 다시 계산한다.
create table dashboard_preset (
  id                  uuid         not null default gen_random_uuid(),
  organization_id     uuid         not null,
  created_by_user_id  uuid         not null,
  name                varchar(100) not null,
  widgets_json        jsonb        not null,
  created_at          timestamptz  not null default now(),
  updated_at          timestamptz  not null default now(),
  constraint pk_dashboard_preset primary key (id),
  constraint uq_dashboard_preset__name unique (organization_id, name),
  constraint fk_dashboard_preset__organization foreign key (organization_id)
    references organization (id) on delete cascade,
  constraint fk_dashboard_preset__user foreign key (created_by_user_id)
    references app_user (id) on delete restrict,
  constraint ck_dashboard_preset__name check (length(btrim(name)) > 0)
);

create index ix_dashboard_preset__org on dashboard_preset (organization_id, name);
