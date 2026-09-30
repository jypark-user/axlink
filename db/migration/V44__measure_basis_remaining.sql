-- 산출 근거가 없던 지표를 채우고, 건수 지표에 "줄이려면" 을 더한다 (QUR.WEB.002).
--
-- V42·V43 은 발주기관이 자주 묻는 지표만 채웠다. 후속 질문("그건 어떻게 해결해?")이
-- 어느 지표로 가든 값의 뜻과 움직이는 조건을 말할 수 있어야 한다. 모델은 이 문장을 풀어
-- 말할 뿐이고 숫자는 만들지 않는다.

update semantic_measure set basis = basis ||
  ' 줄이려면: 도구에서 이슈를 해결·종료 상태로 바꿔야 한다. 다음 수집 때 반영된다.'
where key = 'open_issue_count';

update semantic_measure set basis = basis ||
  ' 줄이려면: 용역사가 WBS 실적 열을 갱신하거나 종료일을 조정해 저장소에 커밋해야 한다.'
where key = 'progress_behind_task_count';

update semantic_measure set basis = basis ||
  ' 올리려면: CI 파이프라인이 실패한 원인을 고쳐 다시 통과시켜야 한다.'
where key = 'test_pass_rate';

update semantic_measure set basis = basis ||
  ' 줄이려면: WBS 산출물 열에 적힌 파일을 저장소에 커밋하거나 산출물 화면에서 그 항목에 올린다.'
where key = 'wbs_deliverable_missing_count';

update semantic_measure set basis = basis ||
  ' 줄이려면: 해당 유형의 산출물을 산출물 화면에서 올리거나 저장소에 커밋해 제출 상태로 만든다. '
  '적용 대상이 아닌 유형은 관리자가 적용 제외로 바꿀 수 있다.'
where key = 'work_product_missing_count';

update semantic_measure set basis =
  'WBS 말단 작업의 종료일이 지났는데 산출물이 없는 작업 수다. 종료일이 남은 미제출은 들지 않는다. '
  '줄이려면: 그 작업의 산출물을 올리거나 커밋하고, 일정이 바뀌었으면 WBS 종료일을 고쳐 커밋한다.'
where key = 'wbs_deliverable_overdue_count';

update semantic_measure set basis =
  '상태를 가리지 않은 전체 이슈 수다. 열린 것과 닫힌 것을 다 센다.'
where key = 'issue_count';

update semantic_measure set basis =
  '종료되지 않은 리스크 수다. 줄이려면: 리스크 도구에서 대응이 끝난 리스크를 종료 상태로 바꾼다.'
where key = 'open_risk_count';

update semantic_measure set basis =
  '변경요청 수다. 상태별로 나눠 접수·검토·반영 흐름을 본다.'
where key = 'change_request_count';

update semantic_measure set basis =
  '수집된 커밋과 머지리퀘스트 수다. 활동량이지 품질이나 진척은 아니다.'
where key = 'code_activity_count';

update semantic_measure set basis =
  '기한이 지났는데 완료되지 않은 시정조치 수다. 줄이려면: 조치를 마치고 도구에서 완료 상태로 바꾼다.'
where key = 'correction_overdue_count';

update semantic_measure set basis =
  '해결된 이슈의 생성부터 해결까지 걸린 일수의 평균이다. 해결되지 않은 이슈는 들지 않는다. '
  '줄이려면: 이슈를 열어 둔 채 오래 두지 않고 처리 즉시 해결 상태로 바꾼다.'
where key = 'issue_avg_resolution_days';

update semantic_measure set basis =
  '해결된 이슈 처리일의 중앙값이다. 절반은 이 안에 닫혔다.'
where key = 'issue_resolution_days_p50';

update semantic_measure set basis =
  '해결된 이슈 처리일의 상위 10% 경계다. 평균이 감추는 오래 걸린 꼬리를 본다.'
where key = 'issue_resolution_days_p90';

update semantic_measure set basis =
  '가장 최근 스냅샷의 해결 이슈 수를 전체 이슈 수로 나눈 값이다. 도구 상태로 잰 관측값이라 신고 진척률과 대조한다.'
where key = 'progress_issue_pct';

update semantic_measure set basis =
  '가장 최근 스냅샷에서 WBS 계획 기간을 오늘 기준으로 안분한 계획선이다. 실적과 무관하게 날짜만으로 정해진다.'
where key = 'progress_planned_pct';

update semantic_measure set basis =
  '가장 최근 스냅샷의 실적 진척률에서 계획 진척률을 뺀 값이다. 음수면 계획보다 늦다. '
  '올리려면: 용역사가 WBS 실적 열을 갱신해 커밋하거나, 계획이 바뀌었으면 WBS 기간을 고쳐 커밋한다.'
where key = 'progress_variance_pct';

update semantic_measure set basis =
  '가장 최근 스냅샷의 WBS 진척률이다. 말단 작업 가중치와 실적의 가중합이며 용역사가 계획서에 적은 자기신고 값이다. '
  '올리려면: 용역사가 WBS 실적 열을 갱신해 저장소에 커밋해야 한다.'
where key = 'progress_wbs_pct';

update semantic_measure set basis =
  '가장 최근 스냅샷에서 제출·승인된 산출물 수를 적용 대상 산출물 수로 나눈 값이다. 파일이 실제로 있는가로 잰 관측값이다. '
  '올리려면: 산출물을 올리거나 저장소에 커밋해 제출 상태로 만든다.'
where key = 'progress_work_product_pct';

update semantic_measure set basis =
  '진척 기록의 실적 진척률에서 계획 진척률을 뺀 값의 평균이다. 음수면 지연이다.'
where key = 'schedule_variance_pct';

update semantic_measure set basis =
  '스냅샷별 검증·인수 완료 요구사항 수를 전체 요구사항 수로 나눈 값이다. 날짜별 추이를 본다. '
  '올리려면: 시험 케이스가 요구사항 코드를 가리키게 하고 시험 결과서(통과)를 올려 검증완료로 바꾼다.'
where key = 'snapshot_requirement_fulfillment_pct';

update semantic_measure set basis =
  '스냅샷별 종료 리스크 수를 전체 리스크 수로 나눈 값이다. 올리려면: 대응이 끝난 리스크를 도구에서 종료 상태로 바꾼다.'
where key = 'snapshot_risk_closed_pct';

update semantic_measure set basis =
  '스냅샷별 승인 산출물 수를 적용 대상 산출물 수로 나눈 값이다. 올리려면: 제출된 산출물을 발주기관이 검토해 승인해야 한다.'
where key = 'snapshot_work_product_approval_pct';
