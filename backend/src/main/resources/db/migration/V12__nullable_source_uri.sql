-- 업로드 문서·시정조치·진척기록·변경요청·회의록은 외부 URL 이 존재하지 않는다.
-- IndexingService 가 이들 원천에 null 을 넣으므로 NOT NULL 이면 색인이 통째로 실패한다.
-- API 계약(MessageSourceResponse.externalUrl)도 이미 nullable 이다.
alter table doc_chunk      alter column source_uri   drop not null;
alter table message_source alter column external_url drop not null;
