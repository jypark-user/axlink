-- 이슈 지표의 이름에 집계 범위를 적는다 (SWFR.WEB.001).
--
-- issue 테이블은 요구사항으로 분류되지 않은 원천 이슈만 담는다. 요구사항 라벨이 붙은
-- GitHub 이슈는 requirement 로 간다. 그런데 이름이 "이슈 건수" 라서 GitHub 의 열린 이슈
-- 수와 견주면 안 맞는다(10-02 대조: GitHub 열림 36 = 요구사항 30 + 일반 6).
-- 키와 산식은 그대로 두고 이름과 산출 근거만 고친다. 사용자가 저장한 위젯 제목은
-- 건드리지 않는다. 위젯 부제는 이 label 을 읽으므로 범위가 거기 드러난다.

update semantic_measure set label = '일반 이슈 건수', basis =
  '요구사항으로 분류된 항목 제외. 상태를 가리지 않은 전체 일반 이슈 수다. 열린 것과 닫힌 것을 다 센다.'
where key = 'issue_count';

update semantic_measure set label = '열린 일반 이슈 수', basis =
  '요구사항으로 분류된 항목 제외. 해결·종료되지 않은 일반 이슈 수다. 도구에서 닫으면 다음 수집 때 줄어든다. '
  '줄이려면: 도구에서 이슈를 해결·종료 상태로 바꿔야 한다. 다음 수집 때 반영된다.'
where key = 'open_issue_count';

update semantic_measure set label = '일반 이슈 처리율', basis =
  '요구사항으로 분류된 항목 제외. 해결(RESOLVED) 또는 종료(CLOSED) 상태인 일반 이슈 수를 전체 일반 이슈 수로 '
  '나눈 값이다. 도구에서 닫은 이슈가 다음 수집 때 반영된다. '
  '올리려면: 도구에서 이슈를 해결·종료 상태로 바꾸면 다음 수집 때 반영된다.'
where key = 'issue_resolution_rate';

update semantic_measure set label = '일반 이슈 평균 처리일', basis =
  '요구사항으로 분류된 항목 제외. 해결된 일반 이슈의 생성부터 해결까지 걸린 일수의 평균이다. '
  '해결되지 않은 이슈는 들지 않는다. '
  '줄이려면: 이슈를 열어 둔 채 오래 두지 않고 처리 즉시 해결 상태로 바꾼다.'
where key = 'issue_avg_resolution_days';

update semantic_measure set label = '일반 이슈 처리일 중앙값', basis =
  '요구사항으로 분류된 항목 제외. 해결된 일반 이슈 처리일의 중앙값이다. 절반은 이 안에 닫혔다.'
where key = 'issue_resolution_days_p50';

update semantic_measure set label = '일반 이슈 처리일 상위 10%', basis =
  '요구사항으로 분류된 항목 제외. 해결된 일반 이슈 처리일의 상위 10% 경계다. '
  '평균이 감추는 오래 걸린 꼬리를 본다.'
where key = 'issue_resolution_days_p90';

update semantic_measure set label = '일반 이슈 해결률(관측)', basis =
  '요구사항으로 분류된 항목 제외. 가장 최근 스냅샷의 해결 일반 이슈 수를 전체 일반 이슈 수로 나눈 값이다. '
  '도구 상태로 잰 관측값이라 신고 진척률과 대조한다.'
where key = 'progress_issue_pct';

update semantic_dimension set label = '일반 이슈 상태' where key = 'issue_status';
update semantic_dimension set label = '일반 이슈 심각도' where key = 'issue_severity';
