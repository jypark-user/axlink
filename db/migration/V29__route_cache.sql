-- 라우팅 캐시 (ARC-014). 같은 질문의 판정(지표·차원·템플릿·목록 종류)을 모델에 다시 묻지 않는다.
-- 판정은 "무엇을 셀지" 이지 값이 아니라 데이터가 바뀌어도 그대로 유효하다. 값은 매번
-- 시맨틱 레이어와 표준 모델에서 새로 뽑는다(절대 규칙 1).
--
-- 키는 정규화한 질문과 카탈로그 버전이다. 지표·차원·템플릿 안내가 바뀌면 버전이 바뀌어
-- 옛 판정은 저절로 안 맞는다. 저장하는 것은 모델이 낸 JSON 원본이다. 읽을 때 다시
-- 검증하므로(from_choice) 카탈로그에서 빠진 키가 살아남지 않는다.

create table route_cache (
  key_hash            char(64)      not null,
  question            text          not null,   -- 정규화한 질문. 사람이 읽고 지우기 위해
  catalog_version     char(64)      not null,
  choice_json         jsonb         not null,
  model               varchar(200)  not null,   -- 어느 모델의 판정인지. 감사 가능성
  hit_count           integer       not null default 0,
  created_at          timestamptz   not null default now(),
  last_hit_at         timestamptz,
  constraint pk_route_cache primary key (key_hash),
  constraint ck_route_cache__choice check (jsonb_typeof(choice_json) = 'object')
);

create index ix_route_cache__version on route_cache (catalog_version);
