-- WBS 계획서 인식 결과 (IM-007 UC-030 3단계·AC-030-4, DEC-04 (b) 2026-11-10 사용자 결정).
--
-- 계획서 판을 처음 읽을 때 무엇을 어떻게 읽었는지 남긴다. 행(wbs_item)만 남기면 열 매핑과
-- 「열이 없습니다」 같은 파싱 경고가 다음 조회부터 사라졌다. 사업마다 마지막으로 읽으려 한 판의
-- 결과 하나다. 읽지 못했으면 status = FAILED 와 사유를 남기고, 행은 직전 판 그대로다(AC-030-3).
-- 열 재지정 기능은 없다(DEC-04 (b)). 고칠 것이 있으면 원본을 고쳐 다시 수집한다.

create table wbs_recognition (
  project_id                uuid         primary key references project(id) on delete cascade,
  work_product_id           uuid,
  status                    varchar(10)  not null check (status in ('OK', 'FAILED')),
  header_row                integer,
  columns_json              jsonb        not null default '[]'::jsonb,
  leaf_count                integer,
  group_count               integer,
  weight_total              numeric(12, 6),
  missing_deliverable_count integer,
  warnings_json             jsonb        not null default '[]'::jsonb,
  error                     text,
  read_at                   timestamptz  not null default now()
);

comment on table wbs_recognition is
  'WBS 계획서 인식 결과. 판을 처음 읽을 때(또는 읽지 못했을 때) 남긴다. 사업당 한 행';
