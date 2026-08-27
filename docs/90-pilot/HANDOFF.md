# AX-Link 작업 인수인계

2026-08-20 기준. 세션 재시작 후 이 문서부터 읽는다.

## 1. 지금까지 확정된 사실 (실측 검증 완료)

| 항목 | 상태 |
| --- | --- |
| PostgreSQL 14 + **pgvector 0.8.0** | 설치·동작 확인. `vector(1024)`, `<=>`, HNSW 정상 |
| 앱 DB `axlink` | Flyway V1·V2 적용 완료. 테이블 33, measure 13, 계정 3 |
| 백엔드 빌드 | `./gradlew build` 성공, jar 생성 확인 |
| 백엔드 기동 | `Started AxLinkApplication` 확인, 8080 응답(미인증 401) |
| 프론트 빌드 | `npm run build` 성공(194KB), vitest 통과 |
| Ollama | 인증 완료, **API 키 불필요** |

### AI 런타임 — 실측으로 확정한 제약

| 모델 | 용도 |
| --- | --- |
| `glm-5.2:cloud` | RAG 합성 · 질의 라우팅 · 위젯 스펙 생성 |
| `deepseek-v4-pro:cloud` | 비정형 문서 정형화 (`:cloud` 태그로만 접근 가능) |
| `bge-m3` | 임베딩, 로컬, **1024차원** |

- **Ollama의 `format` 파라미터(JSON Schema·`"json"`)는 무시된다.** 마크다운 펜스로 감싼 임의 필드명 JSON이 돌아온다.
- **구조화 출력은 반드시 tool calling으로 얻는다.** 두 모델 모두 enum 제약을 정확히 준수함을 확인했다.
- 스트리밍은 SSE가 아니라 **NDJSON**이다. 서버가 SSE로 변환한다.

### RAG 경로 종단 검증 결과

bge-m3 임베딩 3건 적재 후 `<=>` 코사인 검색 — 의미 순위 정확.

| 유사도 | 내용 |
| --- | --- |
| 1.0000 | 요구사항 이행률이 낮은 사업의 산출물 검증 상태를 정리한다 (질의문) |
| 0.4759 | CCTV 실시간 영상 조회 기능의 시험결과서 승인 여부 |
| 0.2797 | 점심 메뉴로 김치찌개를 먹었다 |

한국어 FTS 동작 확인. **22종 밖 산출물 유형 INSERT는 CHECK 제약이 거부**함을 확인.

## 2. 설계 상태

설계 문서 9종 완료([docs/design/](design/)). 설계검증 판정은 **FAIL** (CRITICAL 1, HIGH 5).
지적은 전부 실제 결함이었다.

| 지적 | 내용 | 상태 |
| --- | --- | --- |
| CRITICAL-1 | 프론트 enum이 소문자, DB·Java는 CONSTANT_CASE → **위젯 8종 전부 폴백 렌더** | 프론트 워크플로 지시서에 정정 규칙 반영 |
| HIGH-1 | `contractor_org_id__in` 필터가 JOIN 없이 `tc` 별칭 참조 → 런타임 SQL 오류 | **해소** — `V2__review_fixes.sql` |
| HIGH-2 | `assignee` dimension이 `code_change`에 없는 컬럼 참조 | **해소** — `author` dimension 신설 |
| HIGH-3 | dimension `label_expr`가 SELECT엔 있고 GROUP BY엔 없음 | 미해소 — 통합 테스트로 잡을 것 |
| HIGH-4 | `DocumentStatus` 값이 DB와 불일치 | 프론트 지시서에 6값 확정 반영 |
| HIGH-5 | `Severity`/`TraceEntityType`가 DB 값 집합 미표현 | 프론트 지시서에 반영 |

`V2__review_fixes.sql`은 **멱등**이며 빈 DB에서 V1→V2 체인 적용을 검증했다.

## 3. 남은 작업

1. **백엔드 구현 완료** — 기반(`ai`·`auth`·`common`·`config`) 이후 도메인 5갈래
   (org+project / integration+sync / standard+document / semantic+widget / rag) → 빌드 수정
2. **프론트 구현 완료** — shadcn 컴포넌트 + 타입/API → 화면 3갈래 → 빌드·테스트
3. **테스트·검증** — 워크플로 스크립트 작성 완료, 실행만 남음 (스크래치패드의 `verify.js`)
   - 단위 테스트: 시맨틱 SQL 조립, 22종 enum, Fake 결정성, RRF, 권한
   - 통합 테스트: **카탈로그 전수 SQL 실행**(HIGH-1/2/3 재발 방지), pgvector, 권한 격리
   - 종단 검증: 실기동 후 curl로 API·RAG·위젯생성·문서정형화 확인
   - 최종 보고: `docs/design/06-verification.md`

## 4. 구현 범위 방침

설계는 **349개 클래스**를 정의했으나, 이번 구현은 **모든 계층을 관통하는 수직 슬라이스**로 한정한다.
설계의 클래스명·시그니처·패키지 구조는 따르되 슬라이스에 불필요한 클래스는 만들지 않는다.

## 5. 반드시 지킬 규칙

- **JPA 금지, `JdbcClient` 단독** (설계 C-1)
- **enum은 전 계층 CONSTANT_CASE 단일 표기** (설계 C-2)
- **AI 어댑터는 Ollama + Fake 딱 2벌** (설계 C-3). Anthropic SDK 추가 금지
- 권한 필터(`allowedProjectIds`)는 프롬프트가 아니라 **쿼리 레이어에서 강제**
- 시맨틱 SQL은 문자열 연결 금지 — 화이트리스트 식별자 치환 + 파라미터 바인딩
- 대시보드 레이아웃 단일 원천은 **서버 DB**. localStorage 금지
- 위젯은 데이터(`spec_json`), 닫힌 유니온 타입 금지, 렌더 경로는 spec → 렌더러 1단계
- 프론트 목업 데이터 파일 금지. 모든 UI 컴포넌트는 shadcn/ui
- **코드에 주석을 쓰지 않는다**
- 연동 도구는 **GitHub(형상관리) · Redmine(프로젝트 관리)** 2종으로 확정(2026-08-21). Jira·GitLab·Notion 은 범위 밖
- **초대 메일 자동 발송은 범위 밖**(2026-08-21 확정). 초대 링크를 화면에서 복사해 전달한다

## 6. 이 세션에서 겪은 함정 (반복하지 말 것)

- **에이전트 정체 오판** — 대형 문서 생성 시 트랜스크립트 mtime이 수 분간 멈춘다.
  25초 무활동으로 정지 판정했다가 오진했고, 중복 워크플로를 띄워 산출물을 덮어썼다.
  **정체 판정은 최소 15~20분 기준으로 한다.**
- **동시 워크플로의 파일 충돌** — 두 워크플로가 같은 경로에 쓰면 덮어쓴다.
  소유 경로를 반드시 분리한다.
- **`find -newermt`는 macOS(bfs)에서 동작하지 않는다.** `ls -t` + `stat -f %m`을 쓴다.
- **에이전트가 "이제 작성하겠다"는 텍스트만 남기고 턴을 끝내면 완료로 간주된다.**
  지시서에 "말하지 말고 곧바로 도구를 호출하라"를 넣는다.
- 한 번의 Write에 400줄 이상 담지 않게 지시한다.

## 7. 진행상황 대시보드

```bash
python3 tools/progress_dashboard.py --port 8765
```
