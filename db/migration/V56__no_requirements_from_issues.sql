-- 이슈로 요구사항을 만들지 않는다 (ARC-030)
--
-- 요구사항은 명세서(기준선)로만 만든다. V53 이 기존 연결에 켜 두었던 "이슈로 요구사항 만들기"를
-- 모두 끈다. 코드는 이 열을 더 읽지 않는다. 열은 지우지 않는다(이전 판으로 되돌릴 때 필요하다).
-- 이미 이슈로 만든 요구사항은 그대로 둔다. 그 이슈가 열리고 닫히는 것은 계속 따라간다.
update tool_connection set requirement_from_issues = false where requirement_from_issues;

comment on column tool_connection.requirement_from_issues is
  'ARC-030 부터 쓰지 않는다. 언제나 false. 이전 판 호환을 위해 남긴 열';

-- 지표 산출 근거 문장을 위에 맞춘다. "요구사항으로 분류된 항목" 은 이제 새로 생기지 않는다.
-- 일반 이슈에서 빠지는 것은 명세서 등록 전에 이슈로 만든 요구사항의 출처 이슈뿐이다
update semantic_measure
   set basis = replace(basis, '요구사항으로 분류된 항목 제외.',
                       '명세서 등록 전에 요구사항으로 만든 이슈는 빼고 센다.')
 where basis like '요구사항으로 분류된 항목 제외.%';

update semantic_measure
   set basis = replace(basis, '원천 이슈를 닫으면 구현완료(IMPLEMENTED)까지만 간다.',
                       '출처 이슈가 닫혀도 구현완료(IMPLEMENTED)까지만 간다.')
 where key = 'requirement_fulfillment_rate';
