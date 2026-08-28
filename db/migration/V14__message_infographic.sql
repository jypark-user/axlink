-- 답변에 딸린 인포그래픽을 메시지와 함께 남긴다.
-- SSE 로만 흘리면 대화를 다시 열었을 때 차트가 사라진다.
-- 값은 생성 시점의 스냅샷이다. 지표 정의가 바뀌어도 과거 답변은 그때 보여준 그림을 유지한다.
alter table message add column infographic_json jsonb;
