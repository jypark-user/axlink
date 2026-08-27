-- 시정조치도 다른 표준 엔티티처럼 도구에서 수집한다 (PRD STD-003).
-- 도구 이슈는 기한이 비어 있는 경우가 흔하므로 due_date 를 선택값으로 푼다.
alter table correction_action alter column due_date drop not null;

alter table correction_action
  add column tool_connection_id uuid,
  add column external_id        varchar(200),
  add column external_url       text,
  add column source_kind        varchar(20) not null default 'MANUAL';

alter table correction_action
  add constraint fk_correction_action__connection
    foreign key (tool_connection_id) references tool_connection (id) on delete set null,
  add constraint ck_correction_action__source_kind
    check (source_kind in ('TOOL', 'DOCUMENT', 'MANUAL'));

create unique index uq_correction_action__source
  on correction_action (tool_connection_id, external_id)
  where tool_connection_id is not null and external_id is not null;
