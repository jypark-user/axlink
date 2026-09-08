-- 산출물 자리에 버전을 쌓는다 (SWFR.PIP.009).
--
-- 종전에는 같은 자리에 새 파일이 오면 행을 덮어썼다. 그러면 "계획을 언제 바꿨는가" 에
-- 답할 수 없다. WBS 는 사업 내내 갱신되는 문서라 이 질문이 곧 진척 감독의 본체다.
--
-- 스키마는 원래 누적을 전제로 만들어져 있었다.
--   uq_work_product__version  (project_id, type, version)  ← 버전별 1행
--   uq_work_product__current  (project_id, type) where is_current  ← 현행 1행
-- 막고 있던 것은 원천 유일 인덱스 하나뿐이다. 같은 파일 경로로 두 번째 버전을 넣지 못했다.

drop index uq_work_product__source;

create unique index uq_work_product__source
  on work_product (tool_connection_id, external_id, version)
  where tool_connection_id is not null and external_id is not null;

-- 보관된 원본을 찾는 열쇠. 수집한 파일 본문은 내용 주소로 저장되므로
-- (AXLINK_DOCUMENT_ROOT/<project>/repo/<sha><ext>) 전체 sha 가 있어야 도달한다.
-- version 은 화면에 보이는 짧은 표기라 이 자리를 대신할 수 없다.
alter table work_product add column source_revision varchar(64);

comment on column work_product.source_revision is
  '원천 리비전 식별자(깃 blob sha 등). 보관된 원본 파일을 찾는 열쇠';
