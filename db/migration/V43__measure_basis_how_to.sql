-- 산출 근거에 "올리려면 무엇을 해야 하나" 를 더한다 (QUR.WEB.002).
--
-- "이행률을 높이려면?" 은 발주기관이 실제로 묻는 질문인데 근거 문장이 "왜 0 인가" 까지만
-- 있어 답이 없었다. 값이 움직이는 조건을 행동으로 적는다. 모델은 이 문장을 풀어 말할 뿐이다.

update semantic_measure set basis = basis ||
  ' 올리려면: 시험 케이스가 요구사항 코드를 가리키게 하고 시험 결과서(통과)를 올려 요구사항이 '
  '검증완료로 바뀌게 해야 한다. 이슈를 닫는 것만으로는 구현완료(IMPLEMENTED)까지만 간다.'
where key = 'requirement_fulfillment_rate';

update semantic_measure set basis = basis ||
  ' 올리려면: 시험 케이스에 요구사항 코드(예: SWFR.CON.005)를 적어 추적 링크가 생기게 한다.'
where key = 'requirement_test_trace_rate';

update semantic_measure set basis = basis ||
  ' 올리려면: 도구에서 이슈를 해결·종료 상태로 바꾸면 다음 수집 때 반영된다.'
where key = 'issue_resolution_rate';

update semantic_measure set basis = basis ||
  ' 올리려면: 제출된 산출물을 발주기관이 검토해 승인 상태로 바꿔야 한다. 올리기만 해서는 안 오른다.'
where key = 'work_product_approval_rate';

update semantic_measure set basis = basis ||
  ' 올리려면: WBS 산출물 열에 적힌 파일을 저장소에 커밋하거나 산출물 화면에서 그 항목에 올린다.'
where key = 'wbs_deliverable_submitted_rate';

update semantic_measure set basis = basis ||
  ' 올리려면: 용역사가 사업수행계획서(WBS)의 실적 열을 갱신해 저장소에 커밋해야 한다. 화면에서 고칠 수 없다.'
where key = 'progress_representative_pct';
