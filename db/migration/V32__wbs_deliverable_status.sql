-- WBS 항목의 산출물 제출 판정 (ARC-016 2단계).
--
-- 항목이 정한 산출물이 저장소나 업로드 문서에 있으면 제출, 없으면 미제출, 종료일이 지났는데
-- 없으면 지연이다. 판정은 조회 때 다시 하지만 결과를 행에 남긴다. 시맨틱 레이어와 질의가
-- SQL 로 세야 하고, "왜 제출로 보나" 의 근거(규칙·참조·링크)가 같이 남아야 한다.

alter table wbs_item
  add column deliverable_status varchar(20) not null default 'NONE',
  add column deliverable_rule   varchar(20),   -- REPO_PATH | FILE_NAME | PRODUCT_TYPE
  add column deliverable_ref    text,          -- 맞춘 경로·파일명·산출물 유형
  add column deliverable_url    text,          -- 원문으로 가는 링크
  add column judged_at          timestamptz,
  add constraint ck_wbs_item__deliverable_status
    check (deliverable_status in ('NONE', 'SUBMITTED', 'MISSING', 'OVERDUE'));

-- 시맨틱 카탈로그: WBS 산출물 현황. 22종 산출물 목록(work_product) 과는 다른 축이다.
-- 그쪽은 "사업이 내야 할 산출물 항목", 이쪽은 "WBS 작업이 정한 산출물" 이다.

alter table semantic_measure drop constraint ck_semantic_measure__base_table;
alter table semantic_measure add constraint ck_semantic_measure__base_table check (base_table in (
  'requirement','issue','work_product','risk','code_change','change_request','correction_action',
  'progress_record','progress_snapshot','wbs_item'));

insert into semantic_dimension (key, label, description, select_expr, label_expr, requires_join, value_type) values
('wbs_deliverable_status', 'WBS 산출물 판정', 'WBS 항목의 산출물을 제출·미제출·지연으로 나눈다',
 'e.deliverable_status', null, null, 'CATEGORY');

insert into semantic_filter (key, field, op, label, description, column_expr, value_type, enum_values) values
('wbs_deliverable_status__in', 'wbs_deliverable_status', 'IN', 'WBS 산출물 판정',
 '특정 판정으로 한정한다', 'e.deliverable_status', 'ENUM_LIST', '{SUBMITTED,MISSING,OVERDUE}');

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status) values
('wbs_deliverable_missing_count', 'WBS 미제출 산출물 수',
 'WBS 말단 작업이 정한 산출물 중 아직 없는 것(미제출·지연) 건수. "산출물이 빠진 작업" 질문에 사용',
 'wbs_item', null, 'e.active and e.weight is not null and e.deliverable_status <> ''NONE''',
 'count(*) filter (where e.deliverable_status in (''MISSING'',''OVERDUE''))',
 'COUNT', '건',
 '{project,wbs_deliverable_status}',
 '{project_id__in,wbs_deliverable_status__in}',
 'wbs_deliverable_status', 'ACTIVE'),

('wbs_deliverable_overdue_count', 'WBS 지연 산출물 수',
 'WBS 말단 작업의 종료일이 지났는데 산출물이 없는 건수. "제출이 늦은 산출물" 질문에 사용',
 'wbs_item', null, 'e.active and e.weight is not null and e.deliverable_status <> ''NONE''',
 'count(*) filter (where e.deliverable_status = ''OVERDUE'')',
 'COUNT', '건',
 '{project}',
 '{project_id__in}',
 null, 'ACTIVE'),

('wbs_deliverable_submitted_rate', 'WBS 산출물 제출률',
 'WBS 말단 작업이 정한 산출물 중 제출된 비율(%). "산출물은 얼마나 올라왔나" 질문에 사용',
 'wbs_item', null, 'e.active and e.weight is not null and e.deliverable_status <> ''NONE''',
 'round(100.0 * count(*) filter (where e.deliverable_status = ''SUBMITTED'') / nullif(count(*), 0), 2)',
 'RATE_PCT', '%',
 '{project}',
 '{project_id__in}',
 null, 'ACTIVE');
