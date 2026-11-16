-- DEC-17 (2026-11-16 사용자 결정). WBS 없는 사업(L3)의 대표 진척률을 일반 이슈 해결률에서
-- 「이슈 기반 추정 진척률」로 바꿨다. 대상 일반 이슈의 진척도를 같은 가중치로 평균하고 진척도가
-- 없는 이슈는 0 으로 센다. 해결률은 별도 지표로 남는다(issue_resolved_count / issue_total_count).
--
-- 이미 찍힌 행은 고치지 않는다. 그날 그 산식으로 센 값이 그날의 기록이다. 그래서 대표값이 어떤
-- 산식으로 나왔는지를 새 칸에 적는다. 이 칸이 비어 있는 행은 이 파일 전에 찍힌 것이고, 그중
-- L3 행은 일반 이슈 해결률이다. 추이·비교는 산식이 다르면 그대로 견주지 않는다.

alter table progress_snapshot add column representative_basis varchar(20);
alter table progress_snapshot add constraint ck_progress_snapshot__basis check (
  representative_basis is null
  or representative_basis in ('WBS', 'WBS_ESTIMATED', 'ISSUE', 'ISSUE_PROGRESS', 'WORK_PRODUCT', 'NONE')
);
alter table progress_snapshot add column issue_estimate_pct numeric(6,2);
alter table progress_snapshot add column issue_estimate_missing_count integer;

comment on column progress_snapshot.representative_basis is
  '대표 진척률의 산식. WBS(L1) · WBS_ESTIMATED(L2) · ISSUE_PROGRESS(L3, 이슈 기반 추정 진척률) · '
  'WORK_PRODUCT(L4) · NONE. 비어 있으면 V65 전에 찍힌 행이고, 그때 L3 는 일반 이슈 해결률(ISSUE)이었다';
comment on column progress_snapshot.issue_estimate_pct is
  '이슈 기반 추정 진척률(%). 대상 일반 이슈의 진척도 평균, 결측은 0. 대상이 없거나 진척도가 모두 없으면 null';
comment on column progress_snapshot.issue_estimate_missing_count is
  '진척도가 없어 0 으로 센 대상 이슈 수. 대상 이슈가 없으면 null';

update semantic_measure set
  basis = '가장 최근 일별 스냅샷의 대표 진척률이다. WBS 에 가중치가 있으면 말단 작업 가중치와 '
          '실적의 가중합(L1)이고, 가중치가 없으면 계획 기간 비례 가중치와 실적의 가중합인 추정(L2)'
          '이다. 둘 다 업체가 계획서에 적은 자기신고 실적이다. WBS 가 없으면 이슈 기반 추정 진척률'
          '(L3)이다. 대상 일반 이슈(리스크·결함 제외)의 진척도를 같은 가중치로 평균하고 진척도가 '
          '없는 이슈는 0 으로 센다. 이슈도 없으면 산출물 제출률(L4)이다. 산출물 제출 여부로 WBS '
          '실적을 대신하지 않는다. 2026-11-16 전에 찍힌 L3 스냅샷은 일반 이슈 해결률로 셌으므로 '
          '그 뒤 값과 그대로 견주지 않는다. 스냅샷이 없으면 값이 없다. 올리려면: 용역사가 '
          '사업수행계획서(WBS)의 실적 열을 갱신해 저장소에 커밋해야 한다. 화면에서 고칠 수 없다.',
  updated_at = now()
where key = 'progress_representative_pct';
