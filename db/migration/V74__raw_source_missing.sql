-- 전체 수집 응답에 없던 원본을 「원천 확인 불가」로 표시한다 (IM-007 AC-011-7, DEC-18 (b))
--
-- 원천에서 사라진 것처럼 보여도 HTTP 404·응답 누락만으로는 삭제인지 권한 차이인지 가를 수 없다.
-- 그래서 지우지 않고 그대로 두되, 마지막 전체 수집에 나오지 않았다는 사실만 남긴다. 다시 응답에
-- 나오면 비운다. 실패한 회차·증분 수집·권한이 빠진 종류는 표시하지 않는다(판단할 근거가 아니다).

alter table raw_artifact add column source_missing_at timestamptz;

comment on column raw_artifact.source_missing_at is
  '전체 수집 응답에 이 원본이 없던 첫 시각. 화면은 「원천 확인 불가」로 보인다. 다시 나오면 null';
