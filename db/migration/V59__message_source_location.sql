-- 출처에 원문 위치 문장을 남긴다 (SWFR.RAG.003 · SWFR.RAG.006)
--
-- 출처는 쪽 번호(page_no)만 저장했다. 표제 경로는 조각 머리에 섞여 있었고, 조각이 걸친 끝 쪽이나
-- XLSX 행 범위는 어디에도 없었다. 청크가 재색인으로 사라져도 답변의 출처 위치는 남아야 하므로
-- 사람 말 위치 문장을 출처 행에 같이 둔다. 이전 행은 비어 있고, 화면은 쪽 번호로 대신한다.
alter table message_source add column location text;
