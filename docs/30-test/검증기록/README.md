# 검증 기록 (구조화 데이터)

IM-005 시험계획·결과서의 **원천 데이터**다. 문서 요약(IM-005 7절·9절)은 여기서 다시 만든다.
요구사항 세부 의무 → UC → AC → 시나리오 → 사이클·실행 → 결함 → 수정 → 영향 분석 → 재실행이
한 줄로 이어지도록 파일을 나눴다.

| 파일 | 성격 | 누가 쓰나 |
|---|---|---|
| `catalog.json` | IM-007·IM-007A·구현·검증 대응표에서 **생성**한 정적 카탈로그(UC·AC·시나리오·공통 시나리오·공통 제약·DEC·세부 의무·DEC 영향·시험→AC 초안) | `scripts/verification_records.py catalog` |
| `test-ac-map.csv` | 자동 시험 파일 → AC 연결 **초안**(대응표 산문에서 추출). 실행 기록에 적힌 연결이 우선한다 | 〃 |
| `baseline-*.json` | 사이클 시작 시점의 기준 문서 버전·해시, 코드 커밋, 환경 관측 | 사이클 시작 때 사람(에이전트)이 작성 |
| `cycles.jsonl` | 사이클 1건 1줄: 범위·대상 버전·계획·결과 집계 | 사이클 계획·확정 때 추가 |
| `runs.jsonl` | **시험 실행 1건 1줄**. 덮어쓰지 않는다 | 실행마다 추가 |
| `defects.jsonl` | 결함(제품·자료·명세·환경·정책 미결 구분) | 실패 분석 때 추가, 상태 변경은 새 줄 |
| `impacts.jsonl` | 변경 영향 분석. 어떤 실행을 「재검증 필요」로 돌리는지 | 수정 반영마다 추가 |
| `corrections.jsonl` | 기록 정정. 원 실행은 그대로 두고 정정 사유와 새 판정만 | 필요할 때 추가 |
| `exclusions.jsonl` | 공식 범위 제외. 사용자 승인 기록이 있어야 분모에서 빠진다 | 사용자 결정 뒤 추가 |
| `deployments.jsonl` | 5174·5173 반영 기록(이미지 digest·DB 버전·백업·확인) | 반영마다 추가 |
| `environments.jsonl` | 환경 관측(어느 환경이 어느 버전·DB 로 떠 있는지, 도구 연결·모델) | 관측마다 추가 |
| `status*.{csv,json,md}` | 위 이력에서 **다시 계산**한 현재 상태. 손으로 고치지 않는다 | `scripts/verification_records.py status --md` |
| `cycles/C##-*.md` | 사이클별 계획·결과 서술(사람이 읽는 판) | 사이클마다 |

증거 파일은 저장소 밖 `D:\axlink\var\verify\evidence\<cycle_id>\<run_id>\` 에 두고, 실행 기록에
경로와 SHA-256 을 적는다. 토큰·비밀번호·개인정보는 저장 전에 지우거나 가린다. 작은 텍스트 증거
(API 응답 발췌·명령 출력)는 같은 경로에 두되 큰 파일(덤프·캡처 묶음)은 체크섬만 기록해도 된다.

## 공통 규칙

- **과거 줄은 고치지 않는다.** 잘못 적었으면 `corrections.jsonl` 에 정정 줄을 더한다.
- ID 는 재사용하지 않는다. `C01`, `C01-R0001`, `DEF-V001`, `IMP-001`, `DEP-001`.
  (제품 결함 대장 IM-006 의 `DEF-###` 과 구분하려고 검증 결함은 `DEF-V###` 로 쓴다.
  제품 결함으로 확정되면 IM-006 번호를 `product_defect` 에 적는다.)
- 시각은 ISO 8601, Asia/Seoul 오프셋 포함(`2026-11-05T16:10:00+09:00`).
- 판정 값: `pass` 통과 · `fail` 실패 · `blocked` 실행 차단(환경 손상·선행 실패로 판정 불가) ·
  `not-run` 미실행. 업무상 거절이 기대 결과인 시험은 올바르게 거절하면 `pass`.
- `mode`: `live` 실제(실연동·실모델·실브라우저) · `api` 5174 API 직접 호출 · `auto` 자동 시험 ·
  `replay` 기록 재생 · `mock` 가짜 모델·가짜 도구. `needs` 가 있는 AC 는 `auto`·`replay`·`mock` 만으로
  통과하지 않는다(`pass-mock-only`).
- 한 실행이 여러 AC 를 다루면 `ac_verdicts` 에 AC 별 판정을 적는다. 한 AC 에 필수 시나리오가
  여럿이면 전부 통과해야 그 AC 가 통과다(`status` 가 계산).

## runs.jsonl 한 줄의 필드

| 필드 | 뜻 | 예 |
|---|---|---|
| `run_id` | 실행 ID (사이클-순번) | `C01-R0001` |
| `cycle_id` | 사이클 | `C01` |
| `ts` | 실행 시각 | `2026-11-06T10:00:00+09:00` |
| `operator` | 수행자 | `jypark` / `claude-code` |
| `scenarios` | 시나리오 ID 목록 | `["UC-011-S02"]` |
| `acs` | 다룬 AC | `["AC-011-1","AC-011-2"]` |
| `ac_verdicts` | AC 별 판정 | `{"AC-011-1":"pass","AC-011-2":"fail"}` |
| `obligations` | 세부 의무 ID(카탈로그에서 유도 가능, 적어도 된다) | `["SWFR.CON.005-o1"]` |
| `requirements` | 요구사항 코드 | `["SWFR.CON.005"]` |
| `spec` | 명세·자료 버전 `{im007, im007a, im009, baseline}` | `{"im007":"v0.2.3",…,"baseline":"baseline-2026-11-05"}` |
| `code` | `{commit, api_digest, web_digest, migrate_digest, db_version}` | `{"commit":"645de1d",…,"db_version":"V58"}` |
| `env` | `{name, tools, model}` 실행 환경·도구 연결·모델 | `{"name":"5174","tools":["github:TD-CON-1"],"model":"gemma4:31b-cloud"}` |
| `mode` | 위 `mode` 값 | `api` |
| `start_state` | IM-009 6절 상태 이름과 자료·액터·사업 접근 범위 | `{"state":"S0","actor":"V1","project":"TD-PRJ-1"}` |
| `procedure` | 입력과 실행 절차(명령·요청 요약) | `"POST /connections/{id}/sync …"` |
| `expected` | 기대 결과(명세·IM-009 7절 값) | `"이력 변경 없음, 신규·갱신 0"` |
| `actual` | 실제 결과와 관측한 상태 변화 | `"upserted 274 로 기록됨"` |
| `verdict` | 실행 전체 판정 | `fail` |
| `reason` | 판정 이유(실패·차단·미실행이면 필수) | `"AC-011-2 차이: 전량 재승격 수가 신규·갱신으로 표기"` |
| `evidence` | 증거 `[{path, sha256, kind}]` | `[{"path":"var/verify/evidence/C01/C01-R0001/response.json","sha256":"…","kind":"api"}]` |
| `defects` | 관련 결함 ID | `["DEF-V001"]` |
| `rerun_of` | 재실행이면 이전 실행 ID | `"C01-R0001"` |
| `notes` | 그 밖 | |

## defects.jsonl

`defect_id`, `ts`, `kind`(`product` 제품 결함 · `data` 시험 자료·스크립트 오류 · `spec` 명세 오류 ·
`env` 환경 장애 · `policy` 정책 미결), `title`, `found_in_run`, `acs`, `cause`(원인 분석),
`fix`(`{commits, pr, issue}`), `regression_test`(수정 전 실패·수정 후 통과 시험),
`status`(`open`·`fixed`·`verified`·`wontfix`), `verified_by_run`, `product_defect`(IM-006 번호),
`spec_change_needed`(명세 정정이 필요하면 근거와 승인 필요 여부. 기대값을 임의로 바꾸지 않는다).

## impacts.jsonl

`impact_id`, `ts`, `change`(`{commits, pr, summary}`), `areas`(7절 기준: `api`·`authz`·`common-service`·
`formula`·`schema`·`collect`·`trace`·`document`·`rag`·`ui`·`deploy`), `affected`(`{requirements, ucs, acs,
scenarios}`), `rerun`(다시 돌릴 시나리오), `skip`(다시 돌리지 않는 시나리오와 이유),
`invalidates_runs`(「현재 버전에 대한 재검증 필요」로 돌리는 실행 ID), `full_regression`(true 면 전체 회귀).

## cycles.jsonl

`cycle_id`, `planned_ts`, `closed_ts`, `baseline`, `target_code`(커밋·digest·DB), `scope`(UC·시나리오),
`executable`·`decision_wait`·`env_wait`(계획 때 구분), `result`(통과·실패·차단·미실행 집계),
`plan_doc`(`cycles/C01-계획.md`), `parent_cycle`(중간 수정으로 나눈 하위 사이클이면 부모).

## deployments.jsonl

`dep_id`, `ts`, `env`(`5174`·`5173`), `code`(커밋·digest 3종·DB 버전), `bundle`(포함 UC·기능),
`backup`(`{dump, documents, sha256sums, restore_verified}`), `migration_preverified`, `checks`(외부 주소·
로그인·핵심 기능·데이터 보존), `issues`, `rollback`(문제 때 복구 기록), `approved_by`(5173 은 사용자).

## exclusions.jsonl

`ac`, `ts`, `reason`, `approved_by`(사용자 이름·지시 위치), `decision_ref`(DEC 번호 또는 노트 경로).
`approved_by` 가 없는 줄은 제외로 세지 않는다.

## corrections.jsonl

`correction_id`, `ts`, `run_id`(정정 대상), `verdict`·`ac_verdicts`(새 판정, 바뀐 것만), `reason`.

## 지표 (status 가 계산)

- **전체 완료율** = 통과 AC ÷ (합의된 전체 AC − 승인된 공식 범위 제외). 결정 대기·환경 대기·미실행은 분모에 남는다.
- **실행 시험 통과율** = 통과 실행 ÷ 실제 실행(통과·실패)한 실행. 차단·미실행은 분모에 넣지 않는다.
- **별도 건수** = AC 상태별 건수(fail · blocked · not-run · decision-wait · revalidate · partial · pass-mock-only · excluded).

`decision-wait` 는 「그 AC 가 참조하는 시나리오 가운데 DEC 에 걸린 것이 있고 아직 실행 기록이 없다」는 뜻이다.
DEC 가 AC 의 일부(예: DEC-05 관리자 부분)에만 걸리면 나머지 부분은 실행하고 `ac_verdicts` 에 판정을 적되,
그 AC 전체의 `pass` 는 DEC 결정 뒤 해당 시나리오까지 통과했을 때다.
