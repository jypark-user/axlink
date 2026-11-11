-- 클라우드 위임 모델 구분 (UC-061 1단계, AC-061-4). Ollama 클라우드 모델은 로컬에 껍데기만 있고
-- 생성은 외부 주소로 나간다. /api/tags 가 그 주소를 remote_host 로 준다. 비어 있으면 로컬 모델이다.
-- 폐쇄망 배포에 맞지 않는 모델을 목록에서 구분해 보이려고 남긴다.
alter table llm_model_cache add column remote_host text;
