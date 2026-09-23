-- 올린 문서에 29110 산출물 유형 태그를 단다 (ARC-016 3-3-1).
--
-- 유형은 확정을 요구하지 않는 태그다. 초안이 추정한 값을 사람이 자료 상세에서 바꿀 수 있어야
-- 하는데, 초안 표(structuring_draft)는 확정 흐름의 것이라 거기 쓰면 뜻이 섞인다.
-- 값은 work_product.type 과 같은 22종 코드다. 확정하면 work_product 에도 들어간다.

alter table document_upload
  add column product_type varchar(40),
  add constraint ck_document_upload__product_type check (product_type is null or product_type in (
    'STATEMENT_OF_WORK','PROJECT_PLAN','PROGRESS_STATUS_RECORD','MEETING_RECORD','CHANGE_REQUEST',
    'CORRECTION_REGISTER','ACCEPTANCE_RECORD','PROJECT_REPOSITORY','REPOSITORY_BACKUP','REQUIREMENTS_SPEC',
    'TRACEABILITY_RECORD','SOFTWARE_DESIGN','TEST_CASES_PROCEDURES','SOFTWARE_COMPONENT','SOFTWARE',
    'TEST_REPORT','PRODUCT_OPERATION_GUIDE','SOFTWARE_USER_DOC','SOFTWARE_CONFIGURATION','MAINTENANCE_DOC',
    'VERIFICATION_RESULTS','VALIDATION_RESULTS'));
