# 검증 상태 요약 (2026-11-10)

이 파일은 `python scripts/verification_records.py status --md` 가 이력(runs.jsonl 등)에서 다시 만든다. 손으로 고치지 않는다.

| 지표 | 값 |
|---|---|
| 합의된 전체 AC | 179 |
| 공식 범위 제외(승인 기록 있음) | 0 |
| 통과 AC | 70 |
| **전체 완료율** (통과 AC ÷ 분모 179) | **39.1%** |
| 실행한 시험(통과·실패) | 1413 |
| **실행 시험 통과율** | **82.0%** |
| 재검증 필요로 표시된 실행 | 31 |

## AC 상태별 건수 (별도 건수)

| 상태 | 건수 |
|---|---|
| auto-only | 5 |
| decision-wait | 5 |
| fail | 18 |
| no-scenario | 2 |
| not-run | 12 |
| partial | 35 |
| pass | 70 |
| pass-decision-wait | 9 |
| pass-needs-evidence | 23 |

상태 뜻: pass 통과 · fail 실패 · blocked 실행 차단 · not-run 미실행 · decision-wait 결정 대기(미실행) · pass-decision-wait 근거는 통과했으나 결정 전(미완료) · auto-only 자동 시험만 통과, 명세 시나리오 미실행(미완료) · pass-ci-only 통과했으나 5174 실행 근거 없음(미완료) · revalidate 재검증 필요 · partial 일부만 · pass-needs-evidence 5174 통과했으나 필요한 증거 종류 없음(미완료) · pass-defect-open 통과했으나 걸린 결함이 열림·재확인 전(미완료) · excluded 공식 범위 제외 · no-scenario 시나리오 없음
