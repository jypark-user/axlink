-- 모델 용도 구분 (ARC-022). 답변 모델(LLM) 목록에 임베딩 전용 모델이 섞여 저장될 수 있었다.
-- Ollama /api/tags 가 주는 capabilities(completion·embedding·tools 등)를 그대로 남긴다.
-- 비어 있으면(오래된 서버 등) 용도를 모른다. 그 모델은 짧은 생성 확인을 거쳐야 답변 모델로 저장된다.
alter table llm_model_cache add column capabilities text[];
-- 마지막으로 짧은 생성 확인에 성공한 시각. 저장 직전에 확인한다
alter table llm_model_cache add column verified_at timestamptz;
