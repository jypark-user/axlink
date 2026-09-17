-- 답변 경로에 「현황」을 더한다 (ARC-015). 문서를 가리키지 않는 일반 질문("잘 되고 있어?")과
-- 근거 게이트에 막힌 질문이 사업 현황 그림으로 답을 받는다.

alter table message drop constraint ck_message__route_type;
alter table message add constraint ck_message__route_type
  check (route_type is null or route_type in ('DOCUMENT','AGGREGATE','MIXED','OVERVIEW'));
