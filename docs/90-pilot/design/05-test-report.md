# 05. 실기동 종단 검증 보고서

- 검증 일시: 2026-08-20 23:00 ~ 23:11 (KST)
- 방식: `./gradlew bootRun` 으로 실제 기동 후 **curl 로 HTTP 호출**. 코드 판독이 아니라 실제 응답을 근거로 판정.
- 대상: `kr.co.axlink.AxLinkApplication` / PostgreSQL 14 `axlink` (Flyway V1·V2 적용) / Ollama `http://localhost:11434`
- 로그: `/private/tmp/claude-501/.../scratchpad/axlink-e2e.log`(ollama 어댑터), `axlink-fake.log`(fake 어댑터)

---

## 1. 요약

| 구분 | 건수 |
| --- | --- |
| PASS | 24 |
| FAIL | 6 |
| BLOCKED (외부 요인) | 3 |

기동·인증·프로젝트·시맨틱 위젯·권한 격리는 **실제로 동작**한다.
RAG Q&A 와 문서 정형화는 **AI 이전 단계에서 이미 깨져 있어** 동작하지 않는다(스키마 불일치 / 트랜잭션 경합).
AI 실모델 호출은 Ollama 클라우드 사용량 한도(HTTP 429)로 검증 불가.

---

## 2. 기동

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| 애플리케이션 기동 | PASS | `Started AxLinkApplication in 1.806 seconds`, Tomcat 8080 |
| Flyway | PASS | `Successfully validated 2 migrations`, `Current version of schema "public": 2` |
| DB 연결 | PASS | `HikariPool-1 - Start completed`, `PostgreSQL 14.18` |
| 임베딩 차원 검증 | PASS | `EmbeddingDimensionVerifier : embedding dimension verified: 1024` |

기동 경고(운영 전 조치 필요, 결함 아님):
- `axlink.security.jwt.secret` 미설정 → 일회용 서명키 생성. 재기동 시 발급 토큰 전부 무효.
- `axlink.crypto.master-key` 미설정 → 일회용 키. 재기동 시 기존 암호문 복호화 불가.

---

## 3. 인증 · 인가

| # | 항목 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- |
| T1 | 미인증 `GET /api/projects` | 401 | `401 AUTH_TOKEN_INVALID` | PASS |
| T2 | 로그인 `client@axlink.co.kr / Axlink!2026` | 200 + 토큰 | `200`, accessToken·refreshToken·expiresIn 1800·user 반환 | PASS |
| T3 | 잘못된 비밀번호 로그인 | 401 | `401` | PASS |
| T21 | `POST /api/auth/refresh` | 200 + 신규 토큰 | `200`, 새 accessToken 발급 | PASS |
| T28 | 변조 토큰(서명 훼손) | 401 | `401` | PASS |
| — | `GET /api/auth/me` | 200 | `200`, role·organizationId·allowedProjectIds 반환 | PASS |

`/api/auth/login` 404 문제는 해소됨 — `AuthController` 가 `/login`·`/refresh`·`/logout`·`/me` 를 실제로 서빙한다.

로그인 응답 예시(client):
```json
{"accessToken":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...","refreshToken":"S8wZibll0xdGz56HF9Sa2wQ-nXkPASe-gTejO47F4vs",
 "expiresIn":1800,"user":{"userId":"b0000000-0000-4000-8000-000000000002","email":"client@axlink.co.kr",
 "name":"발주사 담당자","role":"CLIENT","organizationId":"a0000000-0000-4000-8000-000000000002",
 "organizationName":"한국디지털공사","organizationType":"CLIENT",
 "allowedProjectIds":["c0000000-0000-4000-8000-000000000001"],"permissionsByProject":{}}}
```

관찰: `permissionsByProject` 가 `{}` 로 비어 있다. `allowedProjectIds` 는 채워지는데 프로젝트별 권한 맵은 비어 있어,
프론트가 이 맵으로 쓰기 버튼 노출을 결정한다면 전부 비활성화된다. 설계 의도 확인 필요.

---

## 4. 프로젝트

| # | 항목 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- |
| T4 | SUPER_ADMIN 프로젝트 생성 | 201 또는 403 | **500 INTERNAL_ERROR** | FAIL (D1, D2) |
| T4b | CLIENT 프로젝트 생성(필수 4필드) | 201 | `201`, id·defaultDashboardId·metrics 반환 | PASS |
| T5 | 필수 필드 누락(endDate, description) | 400 | `400 VALIDATION_FAILED` + fieldErrors 2건 | PASS |
| T6b | 착수일 > 마감일 | 400 | `400 VALIDATION_FAILED "종료일은 시작일 이후여야 합니다."` | PASS |
| T7 | CONTRACTOR 프로젝트 생성 시도 | 403 | **500 INTERNAL_ERROR** | FAIL (D2) |
| T9 | 프로젝트 목록 | 200 | `200`, 페이징·metrics 포함 | PASS |
| T11 | 소유 프로젝트 상세 | 200 | `200` | PASS |
| T23 | 산출물 목록 | 200 | `200`, `totalCount: 22` (ISO 산출물 마스터 정상) | PASS |
| T24~T27 | 이슈·리스크·추적성·대화 목록 | 200 | 모두 `200` | PASS |

생성 성공 응답:
```json
{"id":"3b5643e9-8c17-4da4-9b31-9da0009ff17f","name":"E2E 검증 프로젝트","status":"PLANNING",
 "startDate":"2026-09-01","endDate":"2027-03-31","defaultDashboardId":"db0f757c-ac45-4069-a9f2-32cb7dd6048d",
 "metrics":{"requirementTotal":0,"workProductTotal":22,...}}
```
프로젝트 생성 시 기본 대시보드와 22종 ISO 산출물이 함께 만들어지는 것까지 실제로 확인됨.

---

## 5. 시맨틱 카탈로그 · 위젯 실행

| # | 항목 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- |
| T12 | `GET /api/semantic/catalog` | 200 | `200`, measure 6종 이상 + allowedDimensions/allowedFilters | PASS |
| T13b | 위젯 preview (measure+dimension) | 데이터 반환 | `200`, 집계값 정상 | PASS |
| T14 | STAT_CARD `open_issue_count` | 200 | `200`, `total.values.value = 0` | PASS |
| T15 | 미허용 dimension `salary` | 거부 | `422 CATALOG_VALIDATION_FAILED "measure 가 허용하지 않는 dimension: salary"` | PASS |
| T22b | `GET /api/dashboards?projectId=` | 200 | `200`, 기본 대시보드 1건 | PASS |
| T29 | 대시보드에 위젯 생성 | 201 | `201`, spec 저장(서버 저장 확인) | PASS |
| T30 | 저장된 위젯 데이터 조회 | 데이터 반환 | `200`, preview 와 동일 집계 | PASS |

검증용으로 `requirement` 5건을 적재(MUST 3건 중 ACCEPTED·VERIFIED 2건)한 뒤 실행한 결과:
```json
{"measure":"requirement_fulfillment_rate","measureLabel":"요구사항 이행률","unit":"%",
 "dimensions":["requirement_priority"],
 "rows":[{"values":{"d0":"COULD","value":0.00}},{"values":{"d0":"SHOULD","value":0.00}},
         {"values":{"d0":"MUST","value":66.67}}],
 "appliedProjectIds":["c0000000-0000-4000-8000-000000000001"],"truncated":false}
```
MUST 3건 중 2건 완료 = 66.67% — **계산이 실제로 맞다.** 시맨틱 계층은 정상 동작.

---

## 6. 권한 격리 (contractor)

contractor 계정은 `c0000000-...-0001` 에만 할당되어 있고, 검증 중 생성한 `3b5643e9-...` 에는 미할당.

| # | 항목 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- |
| T8 | 미할당 프로젝트 상세 조회 | 차단 | `403 PROJECT_ACCESS_DENIED` | PASS |
| T9 | 프로젝트 목록 | 할당분만 노출 | `totalElements: 1` (할당 프로젝트만) | PASS |
| T10 | 미할당 프로젝트 요구사항 | 차단 | `403 PROJECT_ACCESS_DENIED` | PASS |
| T35 | 미할당 프로젝트 스코프 위젯 preview | 차단 | `403 PROJECT_ACCESS_DENIED` | PASS |
| T36 | 미할당 프로젝트 문서 목록 | 차단 | `403` | PASS |
| T37 | 미할당 프로젝트 스코프 대화 생성 | 차단 | `403 PROJECT_ACCESS_DENIED` | PASS |

**프로젝트 단위 데이터 격리는 조회·분석·문서·RAG 진입점 전부에서 일관되게 동작한다.** 누수 없음.

---

## 7. RAG Q&A

| # | 항목 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- |
| — | `bge-m3` 임베딩(로컬) | 1024차원 | `200`, `dim 1024` | PASS |
| — | doc_chunk 적재(3청크, 실임베딩) | 저장 | 3행, `vector_dims = 1024` | PASS |
| — | pgvector 유사도 검색 | 관련 청크 상위 | 정답 청크 1위, `cos_sim 0.7119` | PASS |
| T18 | 대화 생성 | 201 | `201`, projectScope·projectNames 반환 | PASS |
| T19 | `POST /api/conversations/{id}/messages` (SSE) | 스트리밍 + 출처 | **실패 — 응답 없음** | FAIL (D3) |
| T31 | `GET /api/conversations/{id}/messages` | 200 | **500 INTERNAL_ERROR** | FAIL (D3) |
| T33 | fake 어댑터로 재시도 | — | 동일 실패 → AI 무관 확인 | FAIL (D3) |

pgvector 검색 근거:
```
             source_title              |            snippet             | cos_sim
---------------------------------------+--------------------------------+---------
 차세대 통합관제 시스템 요구사항정의서 | 본 사업의 핵심 요구사항은 ...  |  0.7119
 2단계 착수보고서                      | SI 2단계 착수일은 ...          |  0.5105
```
검색·임베딩 계층은 정상. **막힌 지점은 `message` 테이블 저장 단계**(D3). AI 호출까지 도달하지 못한다.

---

## 8. 문서 정형화

| # | 항목 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- |
| T20 | `.txt` 업로드 | 거부 | `415 UNSUPPORTED_FILE_TYPE` (허용: HWP/HWPX/DOCX/XLSX/PDF) | PASS |
| T20b | `.docx` 업로드 | 202 | `202`, status `UPLOADED` | PASS |
| — | 동일 파일 재업로드 | 중복 차단 | `409 DUPLICATE_RESOURCE` (content_hash 기준) | PASS |
| — | 정형화 진행 → DRAFT_READY | 초안 생성 | **`FAILED` / error "대상을 찾을 수 없습니다."** | FAIL (D4) |
| — | `GET /api/documents/{id}/draft` | 404 | **500 (NPE)** | FAIL (D5) |
| T34 | fake 어댑터로 재시도 | — | 동일 `FAILED` → AI 무관 확인 | FAIL (D4) |

국문 요구사항정의서 샘플(SFR-001~004, NFR-001~002, 우선순위 표기 포함)을 DOCX 로 넣었으나,
**텍스트 추출 전에 파이프라인이 죽어** `REQUIREMENTS_SPEC` 판정도 요구사항 추출도 시도되지 않았다.
`extractedCharCount` 가 `null` 인 것이 그 증거다.

---

## 9. AI 실모델 호출 (BLOCKED)

| # | 항목 | 실제 | 판정 |
| --- | --- | --- | --- |
| T17 | AI 위젯 생성(`glm-5.2:cloud`) | `503 AI_UNAVAILABLE "Ollama /api/chat rejected the request with HTTP 429"` | BLOCKED |
| — | RAG 합성(`glm-5.2:cloud`) | 도달 불가(D3 로 선행 차단) + 429 | BLOCKED |
| — | 문서 정형화(`deepseek-v4-pro:cloud`) | 도달 불가(D4 로 선행 차단) + 429 | BLOCKED |

Ollama 직접 호출로 원인 확인:
```
$ curl http://localhost:11434/api/chat -d '{"model":"glm-5.2:cloud",...}'
{"error":"you (klaud9) have reached your session usage limit, upgrade for higher limits: ..."}
HTTP 429
```
`glm-5.2:cloud`, `deepseek-v4-pro:cloud` 모두 429. 20초 간격 4회 재시도, 11분 뒤 재시도 모두 429.
**계정 사용량 한도 문제이며 코드 결함이 아니다.** 로컬 `bge-m3` 는 정상(1024차원 확인).

### 보조 검증 — fake 어댑터로 배선만 확인

실모델을 못 쓰는 대신 `--axlink.ai.adapter=fake` 로 재기동해 AI 앞뒤 배선을 확인했다.
**이것은 실모델 검증이 아니다.** tool calling 자체가 실제로 도는지는 확인되지 않았다.

| 항목 | 결과 |
| --- | --- |
| `POST /api/widgets/generate` | `200`, `status: GENERATED` — 생성된 spec 이 카탈로그 검증을 통과하고 즉시 실행되어 `preview` 에 실데이터 반환 |
| RAG ask | 동일 실패 → D3 는 AI 무관 |
| 문서 정형화 | 동일 실패 → D4 는 AI 무관 |

위젯 생성 응답(fake): 생성 → 카탈로그 검증 → 실행 → preview 반환의 **체인 자체는 연결되어 있다.**
남은 것은 실모델의 tool calling 응답이 이 체인을 통과하는지이며, 이는 미검증이다.

---

## 10. 결함 목록

| ID | 심각도 | 위치 | 증상 | 원인 |
| --- | --- | --- | --- | --- |
| D1 | 중 | `project/web/ProjectController.java:45` | SUPER_ADMIN 이 프로젝트를 생성할 수 없음 | `@PreAuthorize("hasRole('CLIENT')")` 에 SUPER_ADMIN 미포함. 의도라면 403 이 나와야 하는데 D2 때문에 500 |
| D2 | **높음** | `common/error/GlobalExceptionHandler` | 권한 거부가 **403 이 아니라 500 INTERNAL_ERROR** 로 나감 | `AuthorizationDeniedException` 핸들러 부재 → fallback 으로 낙하. 로그: `AuthorizationDeniedException: Access Denied` |
| D3 | **치명** | `rag/repository/ConversationRepository.java` (129, 159, 195, 235, 251, 288행) | RAG Q&A 전체 불능 — 메시지 저장·조회 모두 500 | SQL 이 `message.measure_key` 를 참조하나 V1/V2 스키마에 **해당 컬럼이 없음**. `ERROR: column "measure_key" does not exist` |
| D4 | **치명** | `document/service/DocumentUploadService.java:88` | 업로드 문서가 100% `FAILED` — 문서 정형화 전체 불능 | `@Transactional` 메서드 안에서 `@Async` 인 `pipeline.process(id)` 호출 → 비동기 스레드가 **커밋 전에** 행을 읽어 `findById` 가 빈 값 반환. 커밋 후 실행(`registerSynchronization` / afterCommit)으로 변경 필요 |
| D5 | 중 | `document/service/StructuringService.java:95` | 초안 없는 문서의 `/draft` 조회가 500 | `ApiExceptions.invalidTransition` 에 `to` 가 null 로 전달되어 `NullPointerException: Cannot invoke "java.lang.Enum.name()" because "to" is null` |
| D6 | 중 | `integration/repository/ToolConnectionRepository.java:67` | **동기화 스케줄러가 매 주기 예외로 죽음** — 도구 연동 폴링 미동작 | JdbcClient 에 `java.time.Instant` 를 그대로 바인딩. `PSQLException: Can't infer the SQL type to use for an instance of java.time.Instant`. `Timestamp.from(...)` / `OffsetDateTime` 로 변환 필요 |
| D7 | 낮음 | SSE 엔드포인트 전반 | 비동기/SSE 경로에서 발생한 500 이 클라이언트에는 **`401 AUTH_TOKEN_INVALID (path: /error)`** 로 보임 | 에러 forward 시 `/error` 재요청에 JWT 필터가 다시 걸려 진짜 원인이 가려짐. 디버깅을 크게 방해함 |

우선순위: **D3 · D4 (기능 자체가 없음) → D2 (모든 인가 거부가 500) → D6 → D1 · D5 · D7**

---

## 11. 검증용으로 적재한 데이터 (정리 필요)

`axlink` DB 에 다음을 넣었다. 다른 작업에 방해되면 삭제할 것.

```sql
delete from requirement where code like 'E2E-REQ-%';           -- 5행
delete from doc_chunk where source_uri like 'upload://e2e/%';  -- 3행
delete from project where name = 'E2E 검증 프로젝트';           -- 1행 (cascade)
delete from document_upload where file_name like 'req_spec%.docx';
delete from conversation where title in ('E2E 질의','fake E2E');
```

---

## 12. 결론

- **기동·인증·프로젝트 CRUD·검증·시맨틱 위젯·권한 격리: 실제로 동작한다.** 특히 프로젝트 단위 격리는 6개 진입점에서 빠짐없이 403 을 낸다.
- **RAG Q&A 와 문서 정형화는 현재 동작하지 않는다.** 두 건 모두 AI 이전 단계(D3 스키마 불일치, D4 트랜잭션 경합)에서 끊긴다. AI 어댑터 교체로도 재현되므로 모델 문제가 아니다.
- **AI 실모델 tool calling 은 검증하지 못했다.** Ollama 클라우드 계정 사용량 한도(429) 때문이며, 한도 회복 후 T17·RAG·문서 정형화를 재실행해야 한다. 단, D3·D4 를 먼저 고치지 않으면 재실행해도 AI 호출에 도달하지 못한다.

---

## 13. 재검증 (D1~D7 수정 후)

- 검증 일시: 2026-08-21 09:10 ~ 09:25 (KST)
- 방식: 12절과 동일. `./gradlew bootRun` 실제 기동 후 **curl 로 HTTP 호출**. 코드 판독 아님.
- 포트: **8081** (8080 은 다른 세션의 인스턴스가 점유 중이라 충돌 회피)
- 로그: `.../scratchpad/revalidate.log`(ollama), `fake.log`·`fake2.log`(fake 어댑터)
- **Ollama 429 해소됨.** `glm-5.2:cloud` 직접 호출 `HTTP 200` 확인 → 9절 BLOCKED 3건을 실모델로 재검증할 수 있었다.
- 기동 시 `axlink.crypto.master-key` 는 **Base64 32바이트**여야 한다(임의 문자열은 기동 실패). 재검증은 유효 키를 주입해 기동.

### 13.1 기동

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| 애플리케이션 기동 | PASS | `Started AxLinkApplication in 1.769 seconds`, Tomcat 8081 |
| Flyway | PASS | `Successfully validated 3 migrations`, `Current version of schema "public": 3` (V3 = `message` 컬럼 추가) |
| 임베딩 차원 검증 | PASS | `embedding dimension verified: 1024` |

### 13.2 기존 FAIL 8건 재호출

| # | 결함 | 항목 | 기대 | 실제 응답 | 판정 |
| --- | --- | --- | --- | --- | --- |
| T4 | D1·D2 | SUPER_ADMIN 프로젝트 생성 | 201 또는 403 | `403 {"code":"ROLE_FORBIDDEN"}` | **PASS** |
| T7 | D2 | CONTRACTOR 프로젝트 생성 | 403 | `403 {"code":"ROLE_FORBIDDEN"}` | **PASS** |
| T19 | D3 | SSE 질의 (실모델) | 스트리밍 + 출처 | `HTTP 200`, `event:start`(retrievedChunkCount 3) → `event:delta` 63개 → `event:sources`(각주 1건) → `event:done`(elapsedMs 3171). 합성 답변: "본 사업의 핵심 요구사항은 관제 화면의 실시간 갱신이며, 갱신 주기는 5초 이내로 한다[1]." | **PASS** |
| T31 | D3 | `GET /conversations/{id}/messages` | 200 | `200`, USER·ASSISTANT 2건 + `sources` 각주 복원 | **PASS** |
| T33 | D3 | fake 어댑터 RAG 재시도 | 동작 | `200`, `FAKE(glm-5.2:cloud): 핵심 요구사항은? [1]` 저장·조회 성공 | **PASS** |
| — | D4 | 문서 업로드 → 정형화 | 초안 생성 | `202 UPLOADED` → **`STRUCTURED`, `extractedCharCount: 438`, `draftAvailable: true`**. 초안: `suggestedType REQUIREMENTS_SPEC`, 요구사항 6건(SFR-001~004·NFR-001~002) 우선순위까지 추출 | **PASS** |
| T34 | D4 | fake 어댑터 정형화 재시도 | 동작 | `STRUCTURED`, `extractedCharCount: 117`, 초안 `fake-title` 저장 → **D4 는 AI 무관하게 해소** | **PASS** |
| — | D5 | 초안 없는 문서 `/draft` | 404 | `404 {"code":"RESOURCE_NOT_FOUND","details":{"entity":"structuring_draft"}}`. 없는 문서 id 는 `404 entity:"document"` | **PASS** |

정형화 초안 실제 응답(발췌):
```json
{"status":"PROPOSED","suggestedType":"REQUIREMENTS_SPEC","title":"요구사항정의서",
 "requirements":[{"code":"SFR-001","title":"관제 화면 실시간 갱신","priority":"MUST"},
                 {"code":"SFR-002","title":"장애 발생 SMS 알림","priority":"MUST"},
                 {"code":"SFR-003","title":"관제 대상 장비 관리","priority":"SHOULD"},
                 {"code":"SFR-004","title":"장애 이력 조회","priority":"COULD"},
                 {"code":"NFR-001","title":"응답시간","priority":"MUST"},
                 {"code":"NFR-002","title":"시스템 가용성","priority":"SHOULD"}]}
```

### 13.3 D6 · D7 재확인

| 결함 | 항목 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- |
| D6 | 동기화 스케줄러 | 예외 없이 폴링 | `poll-interval-ms=5000` 으로 기동하고 **ACTIVE `tool_connection` 1건을 실제로 넣어** 확인. 09:23:31 에 `findPollable(Instant)` 가 행을 반환해 `sync_job(POLL)` 이 enqueue·dispatch 됨. 로그 ERROR **0건**, `PSQLException: Can't infer the SQL type` 없음 | **PASS** |
| D7 | SSE 에러가 `/error` 401 로 가려짐 | 진짜 원인 노출 | `/error` 401 가림은 **사라졌다**(아래 상세). 그러나 `Accept: text/event-stream` 일 때 **HTTP 500 + 빈 본문**으로 바뀌었을 뿐 올바른 상태코드가 나오지 않는다 | **FAIL (부분 수정)** |

D6 근거 — 스케줄러가 실제로 돌았다는 증거(더미 자격증명이라 잡 자체는 실패하지만 **스케줄러는 죽지 않는다**):
```
 id                                   | kind | status | err                             | created_at
 1248f959-be02-478d-9fe7-724484c18674 | POLL | FAILED | 자격증명 복호화에 실패했습니다. | 2026-08-21 09:23:31.244598+09
WARN k.c.a.integration.service.SyncRunner : sync job 1248f959-... failed: ApiException
```
(검증용 `tool_connection`·`sync_job` 은 확인 후 삭제함)

D7 근거 — 동일 요청을 Accept 헤더만 바꿔 호출:
```
POST /api/conversations/{없는id}/messages  -H 'Accept: text/event-stream'   → HTTP 500, 본문 없음
POST /api/conversations/{없는id}/messages  -H 'Accept: application/json'    → HTTP 404 RESOURCE_NOT_FOUND
POST /api/conversations/{내것아님}/messages -H 'Accept: text/event-stream'  → HTTP 500, 본문 없음
POST /api/conversations/{id}/messages       토큰 없음                        → HTTP 401 AUTH_TOKEN_INVALID (path 가 /error 아닌 실제 경로)
```
로그 원인:
```
WARN ExceptionHandlerExceptionResolver : Failure in @ExceptionHandler GlobalExceptionHandler#handleApi(ApiException, HttpServletRequest)
org.springframework.web.HttpMediaTypeNotAcceptableException: No acceptable representation
```
→ `produces = text/event-stream` 핸들러에서 던진 예외를 `@ExceptionHandler` 가 **JSON 으로 쓰려다 협상 실패**해 500 으로 떨어진다.
브라우저 `EventSource`/`fetch` 는 `Accept: text/event-stream` 을 보내므로 **실사용 경로에서 그대로 재현된다.**

부수 발견 — SSE 가 **정상 완료된 경우에도** 비동기 dispatch 가 보안 필터 체인을 다시 타면서 요청 1건당 ERROR 스택 4개가 남는다
(클라이언트는 `200` + `event:done` 을 정상 수신하므로 기능 영향은 없음):
```
ERROR o.a.c.c.C.[dispatcherServlet] : Servlet.service() ... threw exception
org.springframework.security.access.AccessDeniedException: Access Denied
  at ...AuthorizationFilter.doFilter(AuthorizationFilter.java:98)
ERROR ... Unable to handle the Spring Security Exception because the response is already committed.
```
D7 의 나머지 절반과 같은 뿌리(비동기 dispatch 에 인증 컨텍스트가 전파되지 않음)로 보인다.

### 13.4 BLOCKED 3건 — Ollama 한도 해소로 실모델 재검증

| # | 항목 | 실제 | 판정 |
| --- | --- | --- | --- |
| T17 | AI 위젯 생성 (`glm-5.2:cloud`) | `200 {"status":"GENERATED"}`, 생성 spec `BAR_CHART / requirement_fulfillment_rate / requirement_priority` 가 카탈로그 검증 통과 후 즉시 실행되어 `MUST 66.67%` 실데이터 반환 | **PASS** |
| — | RAG 합성 (`glm-5.2:cloud`) | T19 참조. 실모델 스트리밍 + 각주 `[1]` 부착 정상 | **PASS** |
| — | 문서 정형화 (`deepseek-v4-pro:cloud`) | 13.2 참조. 문서 유형 판정 + 요구사항 6건 구조화 정상 | **PASS** |

**실모델 tool calling 이 실제로 동작함을 이번에 확인했다.** (12절의 미검증 항목 해소)

### 13.5 기존 PASS 회귀 확인

| 항목 | 실제 | 판정 |
| --- | --- | --- |
| T1 미인증 목록 | `401 AUTH_TOKEN_INVALID` | PASS |
| T2 로그인 (admin/client/contractor) | 3계정 모두 `200` + 토큰, role `SUPER_ADMIN`/`CLIENT`/`CONTRACTOR` | PASS |
| T3 잘못된 비밀번호 | `401 AUTH_CREDENTIALS_INVALID` | PASS |
| T21 refresh / T28 변조 토큰 | `200` / `401` | PASS |
| T4b CLIENT 프로젝트 생성 | `201` + 기본 대시보드 + 산출물 22종 | PASS |
| T5 / T6b 검증 | `400 VALIDATION_FAILED` (fieldErrors 2건) / `400 "종료일은 시작일 이후여야 합니다."` | PASS |
| T8·T10·T35·T36·T37 권한 격리 | 미할당 프로젝트 상세·요구사항·문서·대화 전부 `403 PROJECT_ACCESS_DENIED` | PASS |
| T9 목록 격리 | contractor `totalElements: 1` | PASS |
| T12 시맨틱 카탈로그 | `200`, measure 13종 | PASS |
| T13b·T14 위젯 preview | `MUST 66.67%` / `open_issue_count 0` | PASS |
| T15 미허용 dimension | `422 CATALOG_VALIDATION_FAILED` | PASS |
| T22b·T29·T30 대시보드/위젯 | `200` / `201` / `200` (저장 위젯 데이터 동일 집계) | PASS |
| T20 `.txt` 업로드 | `415 UNSUPPORTED_FILE_TYPE` | PASS |
| 동일 파일 재업로드 | `409 DUPLICATE_RESOURCE` | PASS |
| T23~T27 목록 | 산출물 `totalElements 22`, 이슈·리스크·추적성·대화 모두 `200` | PASS |

**회귀 없음.**

### 13.6 테스트 스위트

```
$ cd backend && ./gradlew test          → BUILD SUCCESSFUL, tests=31 failures/errors=0 skipped=0 (기존 24 → 31, 회귀 테스트 추가됨)
$ cd frontend && npm test               → Test Files 5 passed, Tests 17 passed (17)
$ cd frontend && npm run build          → ✓ built in 2.32s
$ cd backend && ./gradlew build -x test → BUILD SUCCESSFUL
```

### 13.7 재검증 요약

| 구분 | 건수 |
| --- | --- |
| PASS | 12 (기존 FAIL 8건 + D6 + BLOCKED 3건) |
| FAIL | 1 (D7 부분 수정) |
| BLOCKED | 0 |

- **D1·D2·D3·D4·D5·D6 은 실제 HTTP 응답으로 해소 확인.** RAG Q&A 와 문서 정형화가 처음으로 **끝까지 동작한다.**
- **D7 만 남았다.** `/error` 401 가림은 없어졌으나 `Accept: text/event-stream` 요청의 사전 에러가 `500` + 빈 본문으로 나간다. 프론트가 SSE 실패 원인을 여전히 알 수 없다.

### 13.8 미해결 · 신규 관찰

| ID | 심각도 | 위치 | 내용 |
| --- | --- | --- | --- |
| D7-1 | 중 | `AskController` / `GlobalExceptionHandler` | `produces=text/event-stream` 핸들러의 예외가 JSON 협상 실패(`HttpMediaTypeNotAcceptableException`)로 **500 빈 본문**. 404·403·400 이 클라이언트에 전달되지 않음. SSE 경로 전용 에러 렌더링(`text/event-stream` 으로 `event:error` 송출 또는 `produces` 에 `application/json` 병기) 필요 |
| D7-2 | 낮음 | SSE 비동기 dispatch | SSE 정상 완료 시에도 요청당 `AccessDeniedException` ERROR 스택 4개. 기능 영향 없으나 로그 오염. 비동기 dispatch 에 SecurityContext 전파 또는 `ASYNC` dispatch 를 필터에서 제외 필요 |
| D1-r | 낮음 | `ProjectController:45` | `@PreAuthorize("hasRole('CLIENT')")` 유지 → **SUPER_ADMIN 은 프로젝트를 생성할 수 없다.** 500 이 403 이 되어 T4 판정 기준(`201 또는 403`)은 충족하나, 관리자 정책이 의도된 것인지 확인 필요 |
| N1 | 중 | `/api/widgets/generate` | 요청의 `projectScope` 가 생성 spec 에 반영되지 않는다(`"projectScope":[]`). 결과적으로 preview 가 요청한 1개가 아니라 접근 가능한 **전 프로젝트 3건**에 집계된다(`appliedProjectIds` 3건). 권한 밖 유출은 아니나 질의 의도와 다른 값이 나온다 |
| N2 | 낮음 | 로그인 응답 | `permissionsByProject` 가 여전히 `{}` (12절 관찰 그대로) |
