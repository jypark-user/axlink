-- 원천 마일스톤을 표준 모델로 올린다 (GH-130, ARC-023)
--
-- GitHub 마일스톤은 수집됐지만 원본(raw_artifact)에만 있어서 일반 이슈 화면에 보이지 않았다.
-- 이슈 원본 안에도 마일스톤 사본이 있지만, 그 사본은 이슈를 고칠 때만 갱신된다. 마일스톤 기한이나
-- 상태를 바꾸면 사본이 낡는다. 그래서 마일스톤 자체를 표로 두고 이슈는 그 행을 가리킨다.
-- 커넥터는 마일스톤 목록을 매 수집마다 통째로 받으므로 이 표는 늘 최신이다.
--
-- 일정 준수율(SWFR.PIP.007)은 이 표를 읽어 따로 계산한다. 여기서는 저장과 표시만 한다.
create table milestone (
    id                 uuid primary key default gen_random_uuid(),
    project_id         uuid not null references project(id) on delete cascade,
    tool_connection_id uuid references tool_connection(id) on delete set null,
    external_id        varchar(120) not null,
    number             integer,
    title              varchar(500) not null,
    due_on             date,
    state              varchar(20) not null,
    closed_at          timestamptz,
    source_url         varchar(1000),
    source_updated_at  timestamptz,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    constraint ck_milestone__state check (state in ('OPEN', 'CLOSED')),
    constraint uq_milestone__source unique (tool_connection_id, external_id)
);

create index ix_milestone__project on milestone (project_id);

comment on table milestone is '원천 도구의 마일스톤(GitHub milestone). 이름·기한·상태를 원천 그대로 둔다';
comment on column milestone.due_on is '원천 기한. 없을 수 있다';

alter table issue add column milestone_id uuid references milestone(id) on delete set null;
create index ix_issue__milestone on issue (milestone_id) where milestone_id is not null;

comment on column issue.milestone_id is '원천에서 이 이슈에 지정한 마일스톤. 원천에서 빼면 비운다';
