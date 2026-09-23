-- 올린 문서를 WBS 항목에 잇는다 (ARC-016 2단계, 산출물 항목의 원천은 WBS).
--
-- 용역사가 미제출 항목 옆에서 바로 올리면 문서가 그 항목에 붙고, 판정은 이 연결만으로
-- 제출이 된다. 29110 유형 확정을 기다리지 않는다. 유형은 초안이 미리 채우는 태그일 뿐이다.

alter table document_upload
  add column wbs_item_id uuid references wbs_item(id) on delete set null;

create index ix_document_upload__wbs_item on document_upload (wbs_item_id) where wbs_item_id is not null;
