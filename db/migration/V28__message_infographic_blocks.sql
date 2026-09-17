-- 답변에 그림을 여러 개 끼울 수 있게 한다 (ARC-013).
-- message.infographic_json 이 그림 하나를 담은 객체였다. 이제 블록 목록을 담는다.
-- 스키마(jsonb)는 그대로고 안의 모양만 바뀌므로, 기존 행을 한 번 펴 두면 읽는 코드가 한 길이다.

update message
   set infographic_json = jsonb_build_array(infographic_json || '{"slot": 1}'::jsonb)
 where infographic_json is not null
   and jsonb_typeof(infographic_json) = 'object';

alter table message
  add constraint ck_message__infographic_is_array
  check (infographic_json is null or jsonb_typeof(infographic_json) = 'array');
