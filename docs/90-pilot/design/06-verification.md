# 06. 최종 검증 보고서

> **2026-08-21 범위 확정**: 연동 도구는 형상관리 **GitHub** · 프로젝트 관리 **Redmine** 2종으로 확정했다.
> 이 문서의 Jira · GitLab · Notion 관련 서술은 그 시점 이전 기록이며 더 이상 유효하지 않다.
> 현재 범위는 `docs/AX-Link-PRD.md` §1.4 와 `docs/design/02-logical-datamodel.md` §3.5 를 따른다.


| 항목 | 내용 |
| --- | --- |
| 문서 ID | `design/06-verification` |
| 작성 | 2026-08-20 23:16 ~ 23:25 (KST) |
| 대상 | `backend/src` (main 325 파일 / test 7 파일), `frontend/src` (84 파일), `V1__init.sql`·`V2__review_fixes.sql` |
| 방법 | 코드 판독 + `./gradlew cleanTest test` 실제 실행 + `npx vitest run` 실제 실행 + `bootRun` 기동 후 curl 21건 |
| 기동 로그 | `/private/tmp/claude-501/.../scratchpad/boot06.log` |
| **판정** | **조건부 통과 불가** — 표준·분석 계층은 동작, RAG Q&A·문서 정형화는 런타임 불능 |

실행한 검증 명령과 결과는 §6에 그대로 싣는다.

---

## 0. 요약

| 계층 | 상태 |
| --- | --- |
| 기동 · Flyway · DB · 인증 · 권한 격리 | 동작 확인 |
| 표준 점검(STD-001~004) · 추적성 · 거버넌스 | 동작 확인 |
| 시맨틱 레이어 · 위젯 실행 · 대시보드 레이아웃 | 동작 확인 |
| 도구 연동 (Jira/GitLab) | 코드 존재, **폴링 스케줄러 매 주기 예외로 사망** |
| RAG Q&A | **런타임 불능** (스키마 불일치) |
| 문서 업로드 정형화 | **런타임 불능** (트랜잭션 경합) |
| AI 실모델 tool calling | **미검증** (Ollama 429) |

`05-test-report.md` 가 보고한 결함 D1~D7 은 **이번 재검증에서 D6 을 제외하고 전부 그대로 재현**되었다.
D6 은 절반만 고쳐져 있고 실패 경로는 여전히 살아 있다. 그 사이 수정된 것은 프론트엔드 3개 화면과
테스트 5개 파일뿐이다(`find -newermt "2026-08-20 23:11"` 결과 8개 파일, 전부 `frontend/src`).

---

## 1. PRD 기능 ID 대비 달성표

판정 기준: **구현됨** = 백엔드·프론트 양쪽 경로가 있고 실행 근거가 있음 / **부분구현** = 한쪽만 있거나
런타임에서 막힘 / **미구현** = 코드 경로 자체가 없음.

### 1.1 ADM — 조직·계정

| ID | 판정 | 근거 |
| --- | --- | --- |
| ADM-001 조직 관리 | **구현됨** | `org/web/OrganizationController.java` GET·POST·GET{id}·PATCH / `frontend/src/features/admin/organizations-page.tsx` (`api.get('/organizations?size=100')`) |
| ADM-002 계정·Role 부여 | **부분구현** | 계정 생성·역할 부여·초대 재발송은 있음(`org/web/UserController.java` POST `/users`, POST `/users/{id}/invitation-resend`, `frontend/src/features/admin/users-page.tsx`, `features/auth/invite-accept-page.tsx`). **초대 메일은 발송되지 않는다** — `org/service/InvitationSender.java` 는 본문 전체가 `log.info("invitation accept url for user {}: /accept?token={}", ...)` 한 줄이다. 04-design-review MEDIUM-7 미해소 |

### 1.2 PRJ — 프로젝트

| ID | 판정 | 근거 |
| --- | --- | --- |
| PRJ-001 프로젝트 생성 | **구현됨** (단서 있음) | `project/web/ProjectController.java:45` POST + `ProjectCreateRequest` 4필드 필수 / `ProjectLifecycleRuleTest.createRejectsStartDateAfterEndDate` PASS / `frontend/src/features/projects/project-create-page.tsx` + `project-form.test.tsx` 5건 PASS. **단서**: SUPER_ADMIN 은 생성 불가(`@PreAuthorize("hasRole('CLIENT')")`), 그런데 거부가 403 이 아니라 **500** 으로 나간다(§6 V3·V4) |
| PRJ-002 목록·상세 | **구현됨** | `ProjectController.java:36,53` / `ProjectMetrics.java` / `features/projects/project-list-page.tsx`·`project-overview-page.tsx` |
| PRJ-003 용역사 할당 | **부분구현 (조회만 동작 — 등록이 500)** | 화면은 생겼다: `frontend/src/features/assignments/assignments-page.tsx`, `assignment-create-dialog.tsx`, `routes.tsx:31,153` 라우트 + `components/layout/app-sidebar.tsx:90` 네비(CLIENT 전용). 목록 조회는 실동작 — CLIENT(`r2@admin.com`) `GET /api/projects/{id}/assignments` **200**, 할당 2건 반환. **할당 등록이 500 이다** — `POST /api/projects/{id}/assignments` 를 신규 사용자로 호출하면 `INTERNAL_ERROR`. 원인은 `project/repository/ProjectAssignmentRepository.java:36-43` insert 문의 `:permissionsJson` 에 `::jsonb` 캐스트가 없어 jsonb 컬럼(`V1__init.sql:111`)에 varchar 를 넣는 것 — `BadSqlGrammarException`. 같은 프로젝트의 다른 리포지토리(`ToolConnectionRepository.java:28,101`, `SyncJobRepository.java:61,73`, `RawArtifactRepository.java:24`)는 전부 `::jsonb` 를 붙이고 있어 이 파일만 누락이다. 권한 격리는 정상: CONTRACTOR(`r3@admin.com`) 의 POST·PATCH·DELETE 는 **403**(`AssignmentController.java` `@PreAuthorize("hasRole('CLIENT')")`). 단 **GET 목록에는 `@PreAuthorize` 가 없어 CONTRACTOR 도 200 으로 타 계정의 할당·권한을 조회한다** |
| PRJ-004 용역사 권한 제어 | **부분구현 (토글 UI 는 있으나 저장이 500, 표시도 깨짐)** | 토글 UI 는 생겼다: `features/assignments/assignments-page.tsx:145-154` 의 Switch 3종 + `permission-fields.ts`. 로그인 응답에 권한 맵이 실제로 실린다 — contractor 로그인 시 `permissionsByProject: {"c0000000-…-0001": {canConfigureIntegration: true, canUploadDocument: true, canReadDashboard: true}}` (§6 V22, 재확인). **05-test-report 가 "맵이 비어 있다"고 관찰한 것은 CLIENT 계정 기준이며, CLIENT 는 할당 행 자체가 없으므로 정상이다 — 이 지적은 철회한다.** 그러나 실기동에서 결함 2건: ① **권한 PATCH 가 500** — `PATCH /api/projects/{id}/assignments/{aid}` 가 `INTERNAL_ERROR`, 원인은 `ProjectAssignmentRepository.java:84-92` 의 `permissions_json = :permissionsJson` 에 `::jsonb` 누락(PRJ-003 과 동일 뿌리). 토글을 켜고 끌 수 없다. ② **status 대소문자 불일치로 모든 행이 비활성 표시** — 백엔드 `project/service/AssignmentService.java` `toResponses` 가 `a.status().name().toLowerCase()` 로 `"active"` 를 내보내는데, 프론트 `types/api.ts:39` 는 `AssignmentStatus = 'ACTIVE' | 'REVOKED'` 이고 `assignments-page.tsx:134` 가 `a.status === 'ACTIVE'` 로 비교한다. 결과적으로 활성 할당도 "해제됨" 배지가 뜨고 Switch 가 `disabled`, 해제 버튼도 렌더되지 않는다. `app_user.status` 등 다른 enum 은 CONSTANT_CASE(`"INVITED"`)로 나가므로 이 필드만 예외다. `AssignmentResponse.java` 의 `status` 가 enum 이 아니라 `String` 인 것도 함께 고칠 것 |
| PRJ-005 프로젝트 종료 | **구현됨** | `ProjectController.java:67,74` closure-check·close / `standard/web/GovernanceController.java:65,72` acceptance-record / `features/closure/closure-page.tsx` / `ProjectLifecycleRuleTest` 의 `closeIsRejectedWithoutAcceptanceRecord`·`closeSucceedsOnceEveryGateIsSatisfied`·`closeIsRejectedWhileWorkProductsAreUnapproved` 3건 PASS |

### 1.3 INT — 도구 연동·문서

| ID | 판정 | 근거 |
| --- | --- | --- |
| INT-001 연동 등록 | **구현됨** (단서 있음) | 생성 폼이 생겼다: `frontend/src/features/connections/connection-form-dialog.tsx`(등록·수정 겸용) + `connections-page.tsx:126` `POST /projects/{id}/connections`, 테스트 2건 PASS(`connection-form-dialog.test.tsx`). **실기동으로 왕복 확인** — CONTRACTOR(`r3@admin.com`, 해당 프로젝트에 `canConfigureIntegration: true`)로 JIRA 연결 등록 시 **200**, 응답이 `status: "DRAFT"`, `credentialMasked: "****0ken"` 로 자격증명이 마스킹되어 돌아오고 목록 재조회에도 반영, `DELETE /connections/{id}` **204** 로 정리까지 확인. 폼이 보내는 `credential: {email, apiToken, accessToken}` 이 백엔드 `ToolConnectionDtos.CredentialRequest` 와 정확히 일치한다. **단서 2건**: ① 연결 테스트는 실제 아웃바운드 호출을 수행하며 도달 불가 시 **422 `TOOL_RESOURCE_NOT_FOUND`** 를 반환하고 폼이 이를 그대로 노출한다(정상 동작, 다만 실제 Jira 인스턴스로 성공 경로를 확인한 근거는 여전히 없음 — INT-005 와 동일 한계). ② `connections-page.tsx:132` 의 "일시중지" 버튼은 `status !== 'PAUSED'` 이면 무조건 `PAUSED` 를 보내는데, 방금 등록한 `DRAFT` 연결에 대해 백엔드가 **409** 로 거부한다. 등록 직후 이 버튼은 항상 실패한다 |
| INT-002 연결 테스트 | **부분구현** | `ToolConnectionController.java:110,120` POST `/connections/test`·`/connections/{id}/test` + FE 버튼(`connections-page.tsx:79`). **Jira·GitLab 만 실동작** — `integration/adapter/` 아래 구현체는 `jira/JiraConnector`, `gitlab/GitLabConnector`, `fake/FakeToolConnector` 3개뿐인데 `integration/domain/ToolType.java` 는 `JIRA, GITLAB, NOTION, REDMINE` 4종을 선언한다 |
| INT-003 Webhook 발급 | **미구현** | 수신 엔드포인트·시크릿 발급 코드가 없다. 존재하는 것은 `integration/domain/ToolConnection.java:17` 의 `webhookSecretEncrypted` 필드와 `SyncJobKind.WEBHOOK` enum 상수뿐. 컨트롤러 20개 어디에도 webhook 경로 없음 |
| INT-004 동기화 상태 | **부분구현** | `integration/web/SyncJobController.java` 목록·상세·retry·cancel + `features/collection/collection-page.tsx` 재시도 버튼 존재. **그러나 신규 수집이 일어나지 않는다** — 폴링 스케줄러가 매 주기 예외로 죽는다(D6, §2/§6 V13) |
| INT-005 초기 백필 | **부분구현 (미검증)** | `SyncJobKind.BACKFILL`, `integration/service/ToolConnectionService.java`, `integration/service/SyncRunner.java`, `adapter/gitlab/GitLabPaging.java` 로 페이지네이션 경로는 있다. 실제 Jira/GitLab 인스턴스로 실행한 근거가 없다 |
| INT-006 문서 업로드·정형화 | **부분구현 (런타임 불능)** | 파이프라인 코드는 완비: `document/extract/TikaTextExtractor.java`(DOCX·XLSX·PDF), `document/extract/HwpTextExtractor.java`(hwplib 1.1.4 / hwpxlib 1.0.5), `document/service/DocumentPipeline.java`, `StructuringService.java`, `StructuringConfirmService.java`, FE `features/documents/documents-page.tsx`·`structuring-draft-page.tsx`. 확장자 거부는 실제로 동작(§6 V17 `415 UNSUPPORTED_FILE_TYPE`). **업로드한 문서는 100% `FAILED` 가 된다**(§6 V15) — D4 미해소 |

### 1.4 대시보드 (PRD §4.3 — **DSH-nnn ID 는 PRD 에 존재하지 않는다**)

PRD 4.1·4.2·4.4·4.5 는 ID 표를 갖지만 **§4.3 대시보드만 ID 표가 없다**(`grep "DSH-" docs/AX-Link-PRD.md` → 0건).
과제 지시의 "DSH 전 기능 ID"를 만들어 낼 근거가 없어, PRD 소절 번호를 행으로 쓴다.

| PRD 소절 | 판정 | 근거 |
| --- | --- | --- |
| 4.3.1 레이아웃·편집 모드 | **구현됨** | `frontend/package.json` `react-grid-layout ^1.5.0` / `features/dashboard/dashboard-page.tsx:3,23,157` Responsive+WidthProvider / 편집모드 토글·저장·취소(`:124,127,139`) / **서버 저장** `dashboard/web/DashboardController.java:70` PUT `/{id}/layout` (localStorage 미사용) / `layout-mapper.test.ts` 3건 PASS |
| 4.3.2 AI 위젯 생성 3단계 | **부분구현 (백엔드만)** | `dashboard/web/WidgetController.java:39` POST `/widgets/generate` 는 fake 어댑터로 실제 동작 — `200 {"status":"GENERATED", spec:{…}}` (§6 V12). **프론트에 생성 UI 가 없다** — `dashboard-page.tsx` 의 버튼은 저장·취소·편집 3개뿐, `/widgets/generate` 호출 0건. 위젯 추가 자체가 UI 로 불가능 |
| 4.3.3 시맨틱 레이어 | **구현됨** | `semantic/service/SemanticQueryBuilder.java`·`WidgetSpecValidator.java`·`CatalogRegistry.java` / 카탈로그 measure 13종 응답(§6 V6) / 정상 집계 200(§6 V7b) / 미허용 dimension `422 CATALOG_VALIDATION_FAILED`(§6 V8b) / `SemanticCatalogExhaustiveTest` 4건 PASS |
| 4.3.4 위젯 템플릿 8종 | **구현됨** | `features/widgets/renderers.tsx` 8종 + `renderer-registry.ts` (키 전부 CONSTANT_CASE) + `renderer-registry.test.ts` 3건 PASS |

### 1.5 QNA — AI WIKI Q&A

RAG 전 기능이 **D3(스키마 불일치)로 런타임에서 막혀 있다**. 코드 유무와 동작 여부를 분리해 적는다.

| ID | 판정 | 근거 |
| --- | --- | --- |
| QNA-001 대화 생성·목록·삭제·핀 | **부분구현** | 백엔드 4종 전부 존재(`rag/web/ConversationController.java:43,49,65,75`). 생성은 실동작(§6 V5 `201`). **FE 에 삭제·핀 조작이 없다** — `features/ax-query/ask-page.tsx` 사이드바는 `c.pinned ? '📌 '` 로 표시만 하고 토글·삭제 핸들러가 없다 |
| QNA-002 프로젝트 범위 선택 | **구현됨** | 생성 시 `projectScope` 저장·`projectNames` 반환 확인(§6 V5). 미할당 프로젝트 스코프는 `403 PROJECT_ACCESS_DENIED`(05-test-report T37) |
| QNA-003 SSE 스트리밍·중지 | **코드 존재 / 동작 안 함** | `rag/web/AskController.java:54` SSE + `features/ax-query/use-ask-stream.ts` + 중지 버튼(`ask-page.tsx:224`)·중지 배지(`:193`). **메시지 저장 단계에서 500** — D3 |
| QNA-004 출처 카드·딥링크 | **코드 존재 / 동작 안 함** | `features/ax-query/answer-body.tsx:62` `SourceCardList`, 각주 `[n]` ↔ 카드 연동(`:40,160,194`), `message_source` 테이블(V1:801). D3 로 메시지가 저장되지 않아 출처도 생성되지 않는다 |
| QNA-005 추천 질문 칩 | **구현됨** | `rag/service/SuggestionService.java` — 프로젝트 상황을 JdbcClient 로 조회해 컨텍스트로 넣고 `llmPort.callTool` 로 4개 생성, 실패 시 `FALLBACK` 4개. 실호출 `200`(§6 V19). 단 fake 어댑터에서는 FALLBACK 이 반환되므로 **"상태 기반 동적 생성"은 실모델로 미검증** |
| QNA-006 응답 평가 | **코드 존재 / 미검증** | `AskController.java:71` POST `/messages/{id}/feedback` + FE `ask-page.tsx:92,164,172`. D3 로 평가할 메시지가 만들어지지 않아 실행 근거 없음 |

### 1.6 STD — 표준 점검 화면

| ID | 판정 | 근거 |
| --- | --- | --- |
| STD-001 산출물 점검표 22종 | **구현됨** | `standard/web/WorkProductController.java` + `features/deliverables/deliverables-page.tsx:40,46,98` 상태 배지·전이. 프로젝트 생성 시 22종 자동 시드 — 실호출 `totalCount = 22`(§6 V10), `ProjectLifecycleRuleTest.createSeedsTwentyTwoWorkProducts` PASS, `WorkProductTypeSchemaTest.javaEnumMatchesCheckConstraintExactly` PASS |
| STD-002 요구사항 추적 | **구현됨** | `standard/web/TraceabilityController.java:35,41,49,55` + `features/traceability/traceability-page.tsx` 의 `brokenAt` 하이라이트(`:64-66,89`). 실호출 `200` + 행 반환(§6 V20) |
| STD-003 변경·시정 | **구현됨** | `standard/web/GovernanceController.java:34,40,46,53` + `features/changes/changes-page.tsx:49,54,62` 목록·상태 전이 |
| STD-004 검수·종료 | **구현됨** | `GovernanceController.java:65,72` acceptance-record GET·POST + `features/closure/closure-page.tsx:31,37,50,70` + `routes.tsx` closure 라우트가 `RequireRole allow={['CLIENT']}` |

### 1.7 집계

| 판정 | 건수 |
| --- | --- |
| 구현됨 | 14 |
| 부분구현 | 11 |
| 미구현 | 1 (INT-003) |

---

## 2. 설계검증 지적 6건 해소 여부

**6건 전부 해소되었다.** 근거는 아래와 같다.

| ID | 해소 | 근거 |
| --- | --- | --- |
| **CRITICAL-1** 프론트 enum 표기 불일치 | **해소** | `frontend/src/types/api.ts` 가 전부 CONSTANT_CASE: `WidgetTemplate`(`:103` STAT_CARD…GANTT_SUMMARY), `RequirementStatus`(`:45` DEFINED…), `DocumentStatus`(`:78`), `TraceEntityType`(`:65`). `features/widgets/renderer-registry.ts` 의 맵 키 8개 전부 CONSTANT_CASE. `renderer-registry.test.ts` 3건이 이를 고정. 실호출에서도 `template: "BAR_CHART"` 가 그대로 통과(§6 V7b) |
| **HIGH-1** `contractor_org_id__in` JOIN 누락 | **해소** | `V2__review_fixes.sql:1-8` 이 `semantic_filter.requires_join` 컬럼을 추가하고 해당 필터에 `left join tool_connection tc on tc.id = e.tool_connection_id` 를 채운다. `semantic/service/SemanticQueryBuilder.java:41-43` 이 필터의 `requiresJoin()` 을 JOIN 집합에 넣는다. `SemanticCatalogExhaustiveTest.contractorOrgFilterRunsWithoutAnyDimension` PASS |
| **HIGH-2** `assignee` dimension 이 없는 컬럼 참조 | **해소** | `V2__review_fixes.sql:10-19` 가 `author` dimension(`coalesce(e.author, '미지정')`)을 삽입하고 `code_activity_count.allowed_dimensions` 에서 `array_replace(…, 'assignee', 'author')` 로 교체한다. `SemanticCatalogExhaustiveTest.codeActivityCountGroupsByAuthorDimension` PASS |
| **HIGH-3** `label_expr` 가 GROUP BY 에서 누락 | **해소** | `SemanticQueryBuilder.java:57-61` — `labelExpr` 가 있으면 `d{n}_label` 별칭으로 SELECT 에 넣고 **같은 별칭을 `groupBy` 에도 추가**한다(`groupBy.add(labelAlias)`). `SemanticCatalogExhaustiveTest.labelledDimensionsSelectAndGroupByBothExpressions` PASS |
| **HIGH-4** `DocumentStatus` 가 DB 에 없는 값 보유 | **해소** | `types/api.ts:78-84` = `UPLOADED\|EXTRACTED\|STRUCTURED\|CONFIRMED\|REJECTED\|FAILED` 6종. `V1__init.sql:234` `ck_document_upload__status check (status in ('UPLOADED','EXTRACTED','STRUCTURED','CONFIRMED','REJECTED','FAILED'))` — **완전 일치**. 문제였던 `DRAFT_READY` 는 양쪽 어디에도 없다 |
| **HIGH-5** `Severity`·`TraceEntityType` 가 DB 값 집합 미표현 | **해소** | `IssueSeverity`(`:63`) 5종 = `V1:352` `ck_issue__severity`. `RiskLevel`(`:64`) 4종 = `V1:385-387` probability·impact·severity. `TraceEntityType`(`:65-72`) 7종(**`CODE_CHANGE` 포함**) = `V1:443-444` `ck_trace_link__from_type`/`to_type` |

MEDIUM 8건 중 확인한 미해소 2건: **MEDIUM-5**(PRJ-003/004 화면 마운트 지점 — 여전히 화면 자체가 없음), **MEDIUM-7**(ADM-002 초대 메일 — `InvitationSender` 가 로그만 찍음).

---

## 3. 테스트가 보장하는 것과 보장하지 않는 것

실행 결과: 백엔드 **24건 / 6파일 전부 PASS**, 프론트 **17건 / 5파일 전부 PASS**. 실패 0건.
테스트 DB 는 `axlink_test`(`backend/src/test/resources/application-test.yml`), AI 어댑터는 `fake` 고정.

### 3.1 보장하는 것

| 영역 | 테스트 | 실제로 막아 주는 것 |
| --- | --- | --- |
| 시맨틱 카탈로그 | `SemanticCatalogExhaustiveTest` 4건 — 특히 `everyMeasureRunsAloneAndWithEachAllowedDimensionAndFilter` | **13개 measure × 허용 dimension/filter 전 조합을 실제 PostgreSQL 에 실행**한다. HIGH-1~3 같은 "SQL 조립 시 런타임에만 터지는" 결함을 잡는다. 이 저장소에서 가장 값어치 있는 테스트 |
| 프로젝트 데이터 격리 | `ProjectAccessIsolationTest` 5건 | 미할당 프로젝트 행이 목록·집계·요구사항 경로로 새지 않음을 쿼리 계층에서 확인 |
| 프로젝트 수명주기 | `ProjectLifecycleRuleTest` 5건 | 착수일>마감일 거부, 22종 산출물 시드, 검수확인서 없는 종료 거부, 미승인 산출물 있는 종료 거부 |
| pgvector · FTS | `DocChunkVectorSearchTest` 3건 | 1024차원 컬럼이 차원 불일치를 거부, 코사인 정렬이 정답 청크를 1위로, 생성 tsvector 로 전문검색 동작 |
| enum ↔ DDL 정합 | `WorkProductTypeSchemaTest` 2건 (`V1__init.sql` 파일을 직접 읽어 비교) | **`WorkProductType` 한정** — Java enum ↔ CHECK 제약 ↔ `semantic_filter` enum 3자 일치 |
| AI 어댑터 계약 | `FakeAiAdapterTest` 5건 | 임베딩 결정성·정규화·1024차원, 배치 처리, 스트림과 완성본 동일성, tool 호출 인자 스키마 준수 |
| 프론트 | `layout-mapper.test.ts` 3, `sse.test.ts` 5, `project-form.test.tsx` 5, `renderer-registry.test.ts` 3, `App.test.tsx` 1 | 레이아웃 직렬화 왕복, NDJSON/SSE 파서, 생성 폼 검증, 렌더러 키 CONSTANT_CASE 고정 |

### 3.2 보장하지 않는 것 — 여기가 중요하다

| 사각지대 | 결과 |
| --- | --- |
| **HTTP 계층 테스트가 0건이다** | `MockMvc`·`@WebMvcTest`·`RestAssured`·`TestRestTemplate` 사용처가 저장소 전체에 없다. 컨트롤러 20개·엔드포인트 약 70개 중 **테스트가 지나가는 것은 하나도 없다**. 그래서 D1·D2(인가 거부가 403 대신 500)가 전체 PASS 상태에서 그대로 살아 있다 |
| **RAG 영속 계층 테스트가 0건이다** | `rag/repository/ConversationRepository.java` 는 6곳에서 존재하지 않는 컬럼 `message.measure_key` 를 참조한다. `grep measure_key db/migration/` → **0건**. 테스트가 이 저장소를 한 번도 열지 않으므로 D3 는 CI 를 100% 통과한다 |
| **문서 파이프라인 테스트가 0건이다** | `document/` 아래 어떤 클래스도 테스트되지 않는다. D4(커밋 전 `@Async` 읽기)는 테스트로 잡히지 않는다 |
| **연동 계층 테스트가 0건이다** | `integration/` 아래 커넥터·저장소·스케줄러 전부 미테스트. D6(스케줄러 사망)이 무증상으로 통과한다 |
| **enum↔DDL 정합 검사가 1종뿐이다** | `WorkProductType` 만 검사한다. `V1__init.sql` 의 CHECK 제약은 그 외에도 20개 이상이며(`ck_message__status`, `ck_trace_link__link_kind`, `ck_risk__status` …) **어느 것도 Java enum 과 대조되지 않는다.** CRITICAL-1 과 같은 종류의 결함이 재발해도 테스트는 침묵한다 |
| **프론트 타입이 백엔드 DTO 와 대조되지 않는다** | `frontend/src/types/api.ts` 는 손으로 유지되는 사본이다. 계약 생성기도, 대조 테스트도 없다. 지금 일치하는 것은 사람이 맞춰 놓았기 때문이지 구조가 보장해서가 아니다 |
| **실모델 tool calling 이 미검증이다** | AI 관련 테스트 전부 `fake` 어댑터를 쓴다. `glm-5.2:cloud`·`deepseek-v4-pro:cloud` 가 실제로 스키마에 맞는 tool 인자를 돌려주는지는 **한 번도 확인된 적이 없다**(Ollama 429). PRD §2.5·§4.3.3 의 핵심 전제가 미검증 상태 |
| **인증 자체가 미테스트다** | `JwtCodec`·리프레시 토큰 회전·만료·서명 검증에 대한 테스트가 없다. curl 로 확인했을 뿐이다 |
| **프론트 기능 화면이 미테스트다** | 테스트가 렌더하는 컴포넌트는 `App` 과 `ProjectForm` 뿐이다. 13개 feature 화면 중 11개는 렌더조차 되지 않는다. E2E·브라우저 테스트 0건 |

한 줄 요약: **테스트는 "SQL 조립"과 "격리 규칙"과 "수명주기 규칙"을 잘 지킨다. 그 밖의 거의 전부는 지키지 않는다.** 현재 발견된 치명 결함 2건(D3·D4)은 모두 테스트 사각지대에서 나왔다.

---

## 4. 알려진 한계

### 4.1 미해소 런타임 결함 (05-test-report 대비 재검증)

| ID | 05 판정 | **이번 재검증** | 근거 |
| --- | --- | --- | --- |
| D1 SUPER_ADMIN 프로젝트 생성 불가 | 중 | **재현** | `ProjectController.java:46` `@PreAuthorize("hasRole('CLIENT')")` 유지. §6 V4 → 500 |
| D2 인가 거부가 500 | 높음 | **재현** | `common/error/GlobalExceptionHandler.java` 의 `@ExceptionHandler` 8개 중 `AuthorizationDeniedException`·`AccessDeniedException` 핸들러 **없음**(grep 0건). §6 V3 CONTRACTOR 프로젝트 생성 → `500 INTERNAL_ERROR` |
| D3 RAG 스키마 불일치 | 치명 | **재현** | `ConversationRepository.java:129,159,195,235,251,288` 이 `measure_key` 참조. `V1`·`V2` 에 컬럼 없음. §6 V5 메시지 조회 → 500. 기동 로그 411행 `PSQLException: ERROR: column "measure_key" does not exist` |
| D4 문서 파이프라인 트랜잭션 경합 | 치명 | **재현** | `DocumentUploadService.java:62` `@Transactional` 메서드 안 `:88` `pipeline.process(id)` 호출. `afterCommit`·`registerSynchronization` 사용 0건. §6 V15 → `status=FAILED, extractedCharCount=null` |
| D5 draft 조회 NPE | 중 | **재현** | `StructuringService.java:97` `ApiExceptions.invalidTransition(doc.status(), null)` → `ApiExceptions.java:52` 가 `to.name()` 호출. §6 V16 → 500 |
| D6 스케줄러 사망 | 중 | **부분 해소 — 실패 경로는 살아 있음** | `ToolConnectionRepository.java:125` 에 `utc(Instant)` 헬퍼가 추가되어 `updateCursor`·`updateLastVerified` 는 고쳐졌다. **그러나 `findPollable`(`:58-68`)은 `.param("dueBefore", dueBefore)` 로 raw `Instant` 를 그대로 바인딩한다.** 기동 로그 426행 `Unexpected error occurred in scheduled task` → `SyncScheduler.pollAll(SyncScheduler.java:42)`. **고친 두 곳은 애초에 스케줄러가 도달하지 못하는 지점이라, 실질 효과는 0이다** |
| D7 SSE 500 이 401 로 위장 | 낮음 | 미확인 (D3 로 SSE 경로 진입 불가) | — |

### 4.2 설계 대비 구현 범위

`03-physical-backend.md:555` 는 **클래스 합계 349** 를 명시한다. 실제 `backend/src/main/java` 는 **325 파일**이다.
파일 수와 클래스 수는 같은 단위가 아니므로(중첩 record 를 담은 `XxxDtos.java` 는 1파일 다클래스) **이 숫자만으로 "24개 부족"이라 말할 수 없다.** 대신 기능 단위로 빠진 것을 적는다.

| 빠진 것 | 확인 방법 |
| --- | --- |
| Webhook 수신·시크릿 발급 일체 | 컨트롤러 20개 어디에도 webhook 경로 없음 (INT-003) |
| Notion 커넥터 | `integration/adapter/` 에 `notion` 디렉터리 없음. `ToolType.NOTION` 은 선언만 |
| Redmine 커넥터 | 동일. `ToolType.REDMINE` 선언만 |
| 메일 발송 | `JavaMailSender` 의존성·설정 0건 |

### 4.3 미구현 화면 (백엔드 API 는 있으나 프론트 진입점이 없다)

| 화면 | 대응 API |
| --- | --- |
| 용역사 할당·권한 토글 (PRJ-003/004) | `AssignmentController` 4종 |
| 도구 연결 생성 폼 (INT-001) | `POST /projects/{id}/connections` |
| AI 위젯 생성 3단계 마법사 (PRD §4.3.2) | `POST /widgets/generate`, `POST /widgets/preview`, `POST /dashboards/{id}/widgets` |
| 매핑 규칙 편집 (PRD §4.2) | `MappingRuleController` GET·PUT |
| 대화 삭제·핀 토글 (QNA-001) | `DELETE /conversations/{id}`, `PATCH /conversations/{id}` |
| 감사 이력 조회 파라미터 | `AuditPage` 는 존재하나 `GET /api/entity-history` 는 `entityType` 필수 (§6 V21 400). 프로젝트 전체 감사 목록 조회 경로가 없음 |

즉 **대시보드에 위젯을 추가하는 방법이 UI 상 존재하지 않는다.** 프로젝트 생성 시 자동 생성되는 기본 대시보드를 편집·이동만 할 수 있다. 이것이 현재 프론트엔드의 가장 큰 공백이다.

### 4.4 HWP 파싱

- **라이브러리는 실제로 붙어 있다** — `build.gradle:29,30` `kr.dogfoot:hwplib:1.1.4`, `kr.dogfoot:hwpxlib:1.0.5`. `document/extract/HwpTextExtractor.java` 가 HWP 는 `HWPReader` + `TextExtractMethod.InsertControlTextBetweenParagraphText`, HWPX 는 `HWPXReader` + `TextMarks` 로 분기한다. **"HWP 미지원"은 사실이 아니다.**
- **그러나 이 코드는 단 한 번도 실행된 적이 없다.** D4 때문에 파이프라인이 텍스트 추출 이전에 죽는다. 업로드 문서의 `extractedCharCount` 가 항상 `null` 인 것이 그 증거다(§6 V15).
- HWP 전용 테스트도, 샘플 `.hwp` 픽스처도 저장소에 없다.
- hwplib 계열은 표 내부 텍스트·수식·개체 텍스트에서 누락이 알려져 있다. D4 를 고친 뒤 **실제 국문 산출물로 추출 품질을 별도 측정해야 한다.** 현 시점에서 HWP 파싱 품질에 대해 할 수 있는 말은 "미측정"뿐이다.

### 4.5 AI 실모델

`glm-5.2:cloud`·`deepseek-v4-pro:cloud` 모두 계정 사용량 한도(HTTP 429)로 검증하지 못했다. 코드 결함이 아니다.
다만 **PRD 의 핵심 전제 3건이 전부 미검증 상태**로 남는다: (1) tool calling 으로 카탈로그 조합 산출, (2) 22종 산출물 유형 분류, (3) 질의 라우팅. fake 어댑터로 확인한 것은 **배선뿐이며 모델 응답 형식이 아니다.**

### 4.6 운영 안전성

- `axlink.security.jwt.secret` 미설정 시 일회용 서명키 생성 → **재기동하면 발급된 토큰 전부 무효**.
- `axlink.crypto.master-key` 미설정 시 일회용 키 → **재기동하면 저장된 도구 인증정보를 복호화할 수 없다.** 연동 설정이 통째로 못 쓰게 된다. 기동은 성공하므로 운영에서 조용히 사고가 난다.

### 4.7 코드 스타일 편차

프로젝트 규칙은 "DTO 는 도메인별 단일 `XxxDtos.java`"다. 실제로는 절반만 지켜졌다.

| 규칙 준수 | 분리 파일 (규칙 위반) |
| --- | --- |
| `auth/web/AuthDtos.java`, `document/web/DocumentDtos.java`, `integration/web/{MappingRule,SyncJob,ToolConnection}Dtos.java`, `standard/web/StandardDtos.java` (6개) | `dashboard/dto/` 22파일, `rag/dto/` 13파일, `project/web/` 11파일, `org/web/` 6파일, `semantic/dto/` 5파일, `common/web/` 4파일 (**61파일**) |

동작에는 영향이 없지만 두 규약이 공존한다.

### 4.8 데이터 오염

`05-test-report.md §11` 이 지정한 정리 SQL 이 실행되지 않았다. `axlink` DB 에 `E2E-REQ-%` 요구사항 **5행이 남아 있고**, 추적성 API 응답에 그대로 노출된다(§6 V20). 이번 검증에서도 문서·대화·프로젝트가 추가로 생성되었다.

---

## 5. 운영 투입 전 필수 작업 우선순위

| 순위 | 작업 | 위치 | 이유 |
| --- | --- | --- | --- |
| **P0-1** | `message` 테이블에 `measure_key` 추가(V3 마이그레이션) **또는** 저장소 SQL 에서 제거 | `V3__*.sql` / `rag/repository/ConversationRepository.java` 6곳 | RAG Q&A(QNA-003~006) 전체가 이것 하나로 막혀 있다. PRD 4대 기능 중 하나가 통째로 없는 상태 |
| **P0-2** | `pipeline.process(id)` 를 커밋 이후로 이동 (`TransactionSynchronizationManager.registerSynchronization` afterCommit) | `document/service/DocumentUploadService.java:88` | 업로드 문서가 100% 실패한다. INT-006 전체가 막혀 있다 |
| **P0-3** | `AuthorizationDeniedException`·`AccessDeniedException` 핸들러 추가 → 403 | `common/error/GlobalExceptionHandler.java` | 모든 인가 거부가 500 으로 나간다. 보안 사고로 오인되고, 프론트가 403 분기를 못 탄다 |
| **P1-1** | `findPollable` 의 `dueBefore` 를 `utc(...)` 로 감싸기 | `integration/repository/ToolConnectionRepository.java:66` | 도구 연동 폴링이 아예 돌지 않는다. **한 줄 수정** |
| **P1-2** | JWT 서명키·암호화 마스터키를 외부 설정으로 강제(미설정 시 기동 실패) | `config/` | 미설정 기동이 성공해 버려 재기동 시 인증정보 복호화 불가 사고가 난다 |
| **P1-3** | `invalidTransition` 의 `to` null 허용 또는 호출부 수정 | `common/error/ApiExceptions.java:52` / `StructuringService.java:97` | 정상 404 여야 할 요청이 500 NPE |
| **P1-4** | SUPER_ADMIN 프로젝트 생성 허용 여부 확정 후 `@PreAuthorize` 정정 | `project/web/ProjectController.java:46` | 설계 의도 확인 필요. P0-3 을 먼저 고치면 최소한 403 으로 정상화된다 |
| **P2-1** | AI 위젯 생성 UI (3단계 마법사) | `frontend/src/features/widgets/` | **현재 UI 로 위젯을 추가할 방법이 없다.** 대시보드 기능의 절반이 도달 불가 |
| **P2-2** | 용역사 할당·권한 화면 (PRJ-003/004) | `frontend/src/features/projects/` | 백엔드 완비, 화면만 없음. 다중 조직 운영이 불가능 |
| **P2-3** | 도구 연결 생성 폼 (INT-001) | `features/connections/connections-page.tsx` | 새 연동을 UI 로 만들 수 없다 |
| **P2-4** | 대화 삭제·핀 토글 (QNA-001) | `features/ax-query/ask-page.tsx` | 백엔드 완비, 핸들러만 없음 |
| **P2-5** | Ollama 한도 회복 후 T17·RAG·문서 정형화 재실행 | — | P0-1·P0-2 를 먼저 고쳐야 AI 호출에 도달한다. tool calling 실동작이 아직 미검증 |
| **P3-1** | 컨트롤러 계층 테스트 도입(MockMvc), 최소한 인가 거부·에러 코드 경로 | `backend/src/test/` | D1·D2 가 전체 PASS 상태에서 살아남은 원인 |
| **P3-2** | `rag/`·`document/`·`integration/` 저장소 테스트 | 동상 | D3·D4·D6 가 통과한 원인. 세 결함 모두 저장소 한 줄 실행이면 잡혔다 |
| **P3-3** | enum ↔ DDL CHECK 전수 대조 테스트 (`WorkProductTypeSchemaTest` 패턴 확장) | `backend/src/test/` | CRITICAL-1 재발 방지. 현재 CHECK 제약 20여 개가 무검증 |
| **P3-4** | 초대 메일 발송 (ADM-002) | `org/service/InvitationSender.java` | 현재 로그만 남는다. 운영에서 계정 배포가 불가능 |
| **P3-5** | Webhook 수신(INT-003), Notion·Redmine 커넥터 | `integration/` | PRD 명시 기능. 범위 조정 시 명시적으로 제외 선언할 것 |
| **P3-6** | HWP 추출 품질 측정 (실제 국문 산출물 샘플) | `document/extract/` | P0-2 이후. 현재 실행 이력 0회 |
| **P3-7** | `axlink` DB 의 E2E 잔여 데이터 정리 | `05-test-report.md §11` SQL | 추적성 응답에 검증용 행이 노출된다 |

---

## 6. 이번 검증에서 실제로 실행한 명령과 결과

### 6.1 빌드·테스트

```
$ backend/gradlew compileJava compileTestJava     → BUILD SUCCESSFUL (exit 0)
$ backend/gradlew cleanTest test                  → BUILD SUCCESSFUL (exit 0)
$ frontend  npx vitest run                        → Test Files 5 passed / Tests 17 passed (exit 0)
```

백엔드 테스트 결과 XML (`backend/build/test-results/test/`):

| 클래스 | tests | failures | errors |
| --- | --- | --- | --- |
| `ai.FakeAiAdapterTest` | 5 | 0 | 0 |
| `auth.ProjectAccessIsolationTest` | 5 | 0 | 0 |
| `integration.WorkProductTypeSchemaTest` | 2 | 0 | 0 |
| `project.ProjectLifecycleRuleTest` | 5 | 0 | 0 |
| `rag.DocChunkVectorSearchTest` | 3 | 0 | 0 |
| `semantic.SemanticCatalogExhaustiveTest` | 4 | 0 | 0 |
| **합계** | **24** | **0** | **0** |

### 6.2 기동

```
$ backend/gradlew bootRun --args='--axlink.ai.adapter=fake --axlink.security.jwt.secret=… --axlink.crypto.master-key=…'
Current version of schema "public": 2
Tomcat started on port 8080 (http)
Started AxLinkApplication in 1.837 seconds
```

### 6.3 HTTP 검증 21건

| # | 요청 | 결과 | 판정 |
| --- | --- | --- | --- |
| V1 | `POST /api/auth/login` (client) | `200` accessToken 발급 | PASS |
| V2 | `POST /api/auth/login` (contractor) | `200` (token len 328) | PASS |
| V3 | `POST /api/projects` (CONTRACTOR) | **`500 INTERNAL_ERROR`** (기대 403) | **FAIL — D2** |
| V4 | `POST /api/projects` (SUPER_ADMIN) | **`500 INTERNAL_ERROR`** | **FAIL — D1+D2** |
| V5 | `POST /api/conversations` → `GET /{id}/messages` | 생성 `201` / 조회 **`500`** | **FAIL — D3** |
| V6 | `GET /api/semantic/catalog` | `200`, measures 13종 | PASS |
| V7b | `POST /api/widgets/preview` (BAR_CHART + requirement_priority) | `200`, columns·rows 정상 | PASS |
| V8b | `POST /api/widgets/preview` (dimension `salary`) | `422 CATALOG_VALIDATION_FAILED` | PASS |
| V9 | `GET /api/projects/{미할당}` (contractor) | `403 PROJECT_ACCESS_DENIED` | PASS |
| V10 | `GET /api/projects/{id}/work-products` | `200`, total = **22** | PASS |
| V12 | `POST /api/widgets/generate` (fake) | `200 {"status":"GENERATED", spec:{…}}` | PASS (배선만) |
| V13 | 기동 로그 스케줄러 | `ERROR … Unexpected error occurred in scheduled task` → `SyncScheduler.pollAll:42` → `BadSqlGrammarException` on `findPollable` | **FAIL — D6** |
| V14 | `POST /api/projects/{id}/documents` (.docx) | `202`, status `UPLOADED` | PASS |
| V15 | `GET /api/documents/{id}` (수초 후) | `status=FAILED, extractedCharCount=null` | **FAIL — D4** |
| V16 | `GET /api/documents/{id}/draft` | **`500`** (기대 404) | **FAIL — D5** |
| V17 | `POST …/documents` (.txt) | `415 UNSUPPORTED_FILE_TYPE` | PASS |
| V18 | `GET /api/projects` (토큰 없음) | `401 AUTH_TOKEN_INVALID` | PASS |
| V19 | `GET /api/conversations/suggestions` | `200`, 질문 4개 (fake 어댑터 → FALLBACK) | PASS (조건부) |
| V20 | `GET /api/projects/{id}/traceability` | `200`, 행 반환 (E2E 잔여 데이터 노출) | PASS |
| V21 | `GET /api/entity-history?projectId=…` | `400` — `entityType` 필수 | 계약 확인 |
| V22 | `POST /api/auth/login` (contractor) `permissionsByProject` | `{"c0000000-…-0001": {canConfigureIntegration:true, canUploadDocument:true, canReadDashboard:true}}` | PASS — 05 지적 철회 |

**PASS 14 / FAIL 6 / 계약확인 1.**

---

## 7. 결론

- **설계검증 지적 6건(CRITICAL-1, HIGH-1~5)은 전부 해소되었다.** 시맨틱 레이어와 프론트 enum 정합은 코드와 테스트 양쪽에서 확인된다.
- **그러나 05-test-report 가 보고한 런타임 결함은 D6 의 절반을 제외하고 전혀 고쳐지지 않았다.** 그 사이 변경된 파일은 프론트엔드 8개뿐이다.
- **PRD 4대 기능 중 RAG Q&A 와 문서 정형화 2건이 런타임에서 완전히 막혀 있다.** 두 결함(D3·D4) 모두 원인이 특정되어 있고 수정 범위도 작다. AI 모델과는 무관하다.
- **대시보드는 백엔드가 완성되어 있으나 UI 로 위젯을 추가할 수 없다.** 이것이 프론트엔드 최대 공백이다.
- **테스트 24+17건 전부 통과한다는 사실은 품질 근거가 되지 못한다.** 현재 확인된 치명 결함 전부가 테스트 사각지대에서 나왔다. HTTP 계층·RAG 저장소·문서 파이프라인·연동 계층에 테스트가 0건이다.
- **AI 실모델 tool calling 은 여전히 한 번도 검증되지 않았다.** PRD 의 핵심 설계 전제가 미검증인 채로 남아 있다.
