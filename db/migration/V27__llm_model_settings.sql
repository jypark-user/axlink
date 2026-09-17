-- LLM 모델별 토큰 설정 (ARC-011 · SWFR.RAG.002 · QUR.RAG.001).
-- Ollama 는 모델마다 최대 문맥이 다르고, 로컬 장비는 생성이 느려 한 턴의 최대 생성 토큰이
-- 곧 한 턴의 최장 소요 시간이다. 두 값을 코드에 박지 않고 모델별로 저장한다.
--
-- llm_model_cache 는 Ollama /api/tags 응답의 캐시다. 주소를 바꾸거나 새로 고치면
-- 그 주소의 행을 통째로 갈아 끼운다. 실측 생성 속도와 사람이 고른 num_ctx·num_predict 는
-- 같은 행에 붙는다. 모델을 바꾸면 그 모델의 값이 따라온다.

create table llm_model_cache (
  base_url          text          not null,
  name              varchar(200)  not null,
  context_length    integer       not null default 0,  -- 서버가 안 알려주면 0
  supports_tools    boolean       not null default false,
  parameter_size    varchar(40),
  quantization      varchar(40),
  tok_per_sec       numeric(8,2),                       -- 미측정이면 null
  measured_at       timestamptz,
  num_ctx           integer,                             -- 비우면 모델 기본값에 맡긴다
  num_predict       integer       not null default 16000,
  fetched_at        timestamptz   not null default now(),
  updated_at        timestamptz   not null default now(),
  constraint pk_llm_model_cache primary key (base_url, name),
  constraint ck_llm_model_cache__ctx check (num_ctx is null or num_ctx > 0),
  constraint ck_llm_model_cache__predict check (num_predict > 0),
  constraint ck_llm_model_cache__rate check (tok_per_sec is null or tok_per_sec >= 0)
);

-- 지금 쓰는 서버 주소와 모델. 플랫폼 전체에 한 줄이다. 행이 없으면 환경변수 기본값을 쓴다.
create table llm_setting (
  id                 smallint      not null default 1,
  base_url           text          not null,
  model              varchar(200)  not null,
  updated_by_user_id uuid,
  updated_at         timestamptz   not null default now(),
  constraint pk_llm_setting primary key (id),
  constraint ck_llm_setting__single check (id = 1),
  constraint fk_llm_setting__updated_by foreign key (updated_by_user_id) references app_user (id) on delete set null
);
