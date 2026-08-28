-- 산출물 제출 기한. 비어 있으면 기한 없음으로 본다.
alter table work_product add column due_date date;

create index ix_work_product__due on work_product (project_id, due_date)
  where is_current and due_date is not null;
