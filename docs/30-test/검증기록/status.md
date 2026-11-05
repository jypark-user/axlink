# 검증 상태 요약 (2026-11-05)

이 파일은 `python scripts/verification_records.py status --md` 가 이력(runs.jsonl 등)에서 다시 만든다. 손으로 고치지 않는다.

| 지표 | 값 |
|---|---|
| 합의된 전체 AC | 179 |
| 공식 범위 제외(승인 기록 있음) | 0 |
| 통과 AC | 0 |
| **전체 완료율** (통과 AC ÷ 분모 179) | **0.0%** |
| 실행한 시험(통과·실패) | 82 |
| **실행 시험 통과율** | **92.7%** |
| 재검증 필요로 표시된 실행 | 0 |

## AC 상태별 건수 (별도 건수)

| 상태 | 건수 |
|---|---|
| auto-only | 111 |
| decision-wait | 9 |
| fail | 5 |
| no-scenario | 2 |
| not-run | 38 |
| pass-decision-wait | 1 |
| pass-mock-only | 13 |

상태 뜻: pass 통과 · fail 실패 · blocked 실행 차단 · not-run 미실행 · decision-wait 결정 대기(미실행) · pass-decision-wait 근거는 통과했으나 결정 전(미완료) · auto-only 자동 시험만 통과, 명세 시나리오 미실행(미완료) · revalidate 재검증 필요 · partial 일부만 · pass-mock-only 모의·자동만 통과(미완료) · excluded 공식 범위 제외 · no-scenario 시나리오 없음
