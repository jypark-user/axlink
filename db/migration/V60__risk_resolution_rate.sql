-- 위험 처리율 지표 (DEF-V022, IM-007 AC-041-1).
--
-- 다섯 축 가운데 리스크 축은 열린 리스크 수(건수)와 스냅샷 추이(snapshot_risk_closed_pct)만
-- 있었다. 현재 시점의 "리스크를 얼마나 처리했나" 를 물으면 답할 지표가 없었다.
-- 분모는 그 사업의 전체 리스크, 분자는 종료(CLOSED) 리스크다. 대응 중(MITIGATING)은 처리로
-- 세지 않는다. 리스크가 없으면 nullif 로 값이 비고 화면은 산출 불가로 보인다.

insert into semantic_measure (key, label, description, base_table, join_clause, row_filter,
                              value_expr, value_type, unit, allowed_dimensions, allowed_filters,
                              default_dimension, status, basis) values
('risk_resolution_rate', '위험 처리율',
 '전체 리스크 중 종료된 리스크 비율(%). "리스크 처리율", "위험 처리율" 질문에 사용. '
 '열린 리스크 수와 다르다',
 'risk', null, null,
 'round(100.0 * count(*) filter (where e.status = ''CLOSED'') / nullif(count(*), 0), 2)',
 'RATE_PCT', '%',
 '{project,risk_severity}',
 '{project_id__in,risk_severity__in}',
 'project', 'ACTIVE',
 '수집한 리스크 전체를 분모로, 종료 상태인 리스크를 분자로 한다. 대응 중인 리스크는 처리로 '
 '세지 않는다. 리스크가 한 건도 없으면 산출할 수 없다. 올리려면: 리스크 도구에서 대응이 '
 '끝난 리스크를 종료 상태로 바꾼다. 다음 수집 때 반영된다.');
