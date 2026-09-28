-- 지표에 산출 근거를 붙인다 (QUR.WEB.002).
--
-- "요구사항 이행률 0%" 만 나오면 발주기관은 왜 0 인지 모른다. 지표마다 사람 말로 된 근거
-- (무엇을 무엇으로 나누는지, 값이 언제 움직이는지)와 분자·분모 식을 둔다. 답변과 위젯이
-- 같은 근거를 보인다. 분자·분모는 비율 지표에만 있고, 값과 같은 집계 단위로 센다.

alter table semantic_measure
  add column basis           text,
  add column numerator_expr  text,
  add column denominator_expr text;

update semantic_measure set
  basis = '검증완료(VERIFIED) 또는 인수완료(ACCEPTED) 상태인 요구사항 수를 전체 요구사항 수로 나눈 값이다. '
          '요구사항은 시험 결과가 연결되어야 검증완료로 올라간다. 시험 결과가 아직 수집되지 않았으면 '
          '분자가 0 이라 0% 다. 구현이 끝났는지(IMPLEMENTED)와는 다른 지표다.',
  numerator_expr = 'count(*) filter (where e.status in (''VERIFIED'',''ACCEPTED''))',
  denominator_expr = 'count(*)'
where key = 'requirement_fulfillment_rate';

update semantic_measure set
  basis = '시험(TESTS) 추적 링크가 하나라도 붙은 요구사항 수를 전체 요구사항 수로 나눈 값이다. '
          '시험 케이스가 요구사항 코드를 가리켜야 링크가 생긴다.',
  numerator_expr = 'count(distinct e.id) filter (where tl.id is not null)',
  denominator_expr = 'count(distinct e.id)'
where key = 'requirement_test_trace_rate';

update semantic_measure set
  basis = '해결(RESOLVED) 또는 종료(CLOSED) 상태인 이슈 수를 전체 이슈 수로 나눈 값이다. '
          '도구에서 닫은 이슈가 다음 수집 때 반영된다.',
  numerator_expr = 'count(*) filter (where e.status in (''RESOLVED'',''CLOSED''))',
  denominator_expr = 'count(*)'
where key = 'issue_resolution_rate';

update semantic_measure set
  basis = '적용 대상인 산출물 항목(ISO 29110 22종) 중 승인 완료(APPROVED) 인 항목 수를 적용 대상 수로 나눈 값이다. '
          '제출만 된 것은 분자에 들지 않는다.',
  numerator_expr = 'count(*) filter (where e.status = ''APPROVED'')',
  denominator_expr = 'count(*)'
where key = 'work_product_approval_rate';

update semantic_measure set
  basis = 'CI 파이프라인 실행 중 성공한 횟수를 전체 실행 횟수로 나눈 값이다. 요구사항별 시험 결과가 아니라 '
          '빌드·자동 시험의 성공률이다. 파이프라인 기록이 수집되지 않으면 값이 없다.',
  numerator_expr = 'count(*) filter (where e.state = ''SUCCESS'')',
  denominator_expr = 'count(*)'
where key = 'test_pass_rate';

update semantic_measure set
  basis = 'WBS 말단 작업이 정한 산출물 중 제출로 판정된 수를 산출물이 정해진 작업 수로 나눈 값이다. '
          '저장소 경로·파일 이름·항목에 붙인 문서·산출물 유형 순으로 맞춰 본다.',
  numerator_expr = 'count(*) filter (where e.deliverable_status = ''SUBMITTED'')',
  denominator_expr = 'count(*)'
where key = 'wbs_deliverable_submitted_rate';

update semantic_measure set
  basis = '가장 최근 일별 스냅샷의 대표 진척률이다. WBS 가 있으면 말단 작업 가중치와 실적의 가중합(L1)이고, '
          '업체가 계획서에 적은 자기신고 값이다. 스냅샷이 없으면 값이 없다.'
where key = 'progress_representative_pct';

update semantic_measure set
  basis = '오늘 기준 계획선(기간 안분)보다 실적이 뒤진 WBS 말단 작업 수다. 가장 최근 스냅샷 값이다.'
where key = 'progress_behind_task_count';

update semantic_measure set
  basis = '적용 대상인 산출물 항목(ISO 29110 22종) 중 상태가 없음(NONE) 인 항목 수다. WBS 가 정한 산출물과는 다른 축이다.'
where key = 'work_product_missing_count';

update semantic_measure set
  basis = 'WBS 말단 작업이 정한 산출물 중 아직 없는 것(미제출·지연) 수다.'
where key = 'wbs_deliverable_missing_count';

update semantic_measure set
  basis = '해결·종료되지 않은 이슈 수다. 도구에서 닫으면 다음 수집 때 줄어든다.'
where key = 'open_issue_count';
