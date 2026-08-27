export const meta = {
  name: 'ax-link-implement',
  description: 'AX-Link 백엔드 도메인 5갈래 + 프론트 화면 3갈래 구현 → 빌드 통과',
  phases: [
    { title: '구현', detail: '백엔드 도메인 5 + 프론트 인프라 1 (병렬)' },
    { title: '화면', detail: '프론트 화면 3 (병렬, 인프라 이후)' },
    { title: '빌드', detail: '백엔드·프론트 빌드 수정 (병렬)' },
  ],
}

const ROOT = '/Users/userinsight-design/Documents/SourceCode/ax-link'
const D = `${ROOT}/docs/design`
const BE = `${ROOT}/backend`
const FE = `${ROOT}/frontend`
const SCHEMA = `${BE}/src/main/resources/db/migration/V1__init.sql`
const SCHEMA2 = `${BE}/src/main/resources/db/migration/V2__review_fixes.sql`

const RULES = `
# 절대 규칙 (위반 시 빌드/검증 실패)
- **JPA 금지. \`org.springframework.jdbc.core.simple.JdbcClient\` 단독.** Repository 는 JdbcClient 직접 사용 또는 \`kr.co.axlink.common.support.JdbcSupport\`(one/list/exists) 사용.
- **enum 은 전 계층 CONSTANT_CASE 단일 표기** (DB CHECK 제약값과 정확히 일치). 소문자 금지.
- **AI 어댑터는 Ollama + Fake 둘만 존재** (이미 구현됨). Anthropic/OpenAI SDK 추가 금지. AI 기능은 \`kr.co.axlink.ai.port.*\` 포트를 통해 접근.
- **권한: \`allowedProjectIds\` 는 프롬프트가 아니라 쿼리 레이어에서 강제.** \`kr.co.axlink.auth.security.ProjectAccessResolver\` 를 주입받아 \`allowedProjectIds(principal)\` / \`requireProject(p, id)\` / \`requirePermission(p, id, AssignmentPermission.X)\` 사용.
- **시맨틱 SQL 은 문자열 연결 금지** — 화이트리스트 식별자 치환(measure/dimension/filter key 는 카탈로그에서 조회한 값만 허용) + 값은 파라미터 바인딩. SQL 인젝션 문자열이 식별자로 통과하면 안 됨.
- **대시보드 레이아웃 단일 원천은 서버 DB.** localStorage 금지.
- **위젯은 \`spec_json\` 데이터 기반, 닫힌 유니온 타입 금지, 렌더 경로는 spec → 렌더러 1단계.**
- 프론트: 목업 데이터 파일 금지. 모든 UI 컴포넌트는 shadcn/ui. \`fetch\` 직접 호출 금지 — \`api/client.ts\` 사용.
- **연동 도구는 GitHub(형상관리) · Redmine(프로젝트 관리) 2종뿐이다.** Jira·GitLab·Notion 은 범위 밖.
- **코드에 주석을 일절 쓰지 않는다.** (Javadoc 포함)
- **"이제 작성하겠다" 같은 말만 하고 턴을 끝내지 마라.** 곧바로 Read/Write/Edit 도구를 호출하라.
- **한 번의 Write 에 400줄 이상 넣지 마라.** 큰 파일은 여러 번에 나눠 Write 하거나 Edit 으로 이어 붙인다.
- **\`./gradlew\` 와 \`npm run\` 을 직접 실행하지 마라.** (동시 빌드 충돌 방지) 코드만 작성. 빌드는 빌드 단계 에이전트가 단독 실행.
`

const FOUNDATION = `
# 기반 클래스 (이미 구현됨 — 재작성 금지, 재사용)
- \`kr.co.axlink.common.support.JdbcSupport\` — one(sql,params,type)/list(...)/exists(sql,params). @Component.
- \`kr.co.axlink.common.error.ApiExceptions\` — validationFailed/credentialsInvalid/roleForbidden/projectAccessDenied/assignmentPermissionDenied/notFound(entity,id)/duplicate/invalidTransition(from,to)/projectClosed(id)/catalogValidationFailed/toolAuthFailed/toolUnreachable/syncJobConflict/aiUnavailable/aiToolCallFailed/internal. \`ApiException\`, \`ErrorCode\`.
- \`kr.co.axlink.common.web\` — \`PageQuery(page,size,sort)\`(.offset()/.limit()/.first()), \`PageResponse<T>\`(.of(content,q,total)), \`SortSpec\`, \`UpdatedAtRule\`.
- \`kr.co.axlink.common.json.JsonCodec\` — read(json,Class)/write(obj). @Component.
- \`kr.co.axlink.common.crypto.SecretCipher\`, \`CryptoProperties\` — 연동 자격증명 암호화.
- \`kr.co.axlink.common.support.Backoff\`, \`Hashes\`.
- \`kr.co.axlink.auth.domain\` — \`AuthPrincipal(userId, organizationId, OrgType orgType, Role role)\` (record), \`AssignmentPermissions\`(record: canConfigureIntegration/canUploadDocument/canReadDashboard), \`RefreshToken\`.
- \`kr.co.axlink.auth.security\` — \`ProjectAccessResolver\`(@Component @RequestScope; allowedProjectIds/resolveScope/requireProject/requirePermission/permissionsByProject), \`JwtCodec\`, \`JwtProperties\`, \`JwtAuthenticationFilter\`, \`SecurityErrorWriter\`.
- \`kr.co.axlink.ai.port\` — \`EmbeddingPort\`(embed(text):float[]), \`LlmPort\`(stream(LlmRequest, Flux<LlmDelta>)/complete(LlmRequest):LlmResponse/structured(LlmRequest, ToolSchema):ToolInvocation), \`LlmRequest\`, \`LlmResponse\`, \`LlmMessage\`, \`LlmRole\`, \`LlmDelta\`, \`LlmModels\`, \`ToolRequest\`, \`ToolSchema\`, \`ToolInvocation\`.
- \`kr.co.axlink.ai.prompt.Prompts\`, \`kr.co.axlink.ai.prompt.ToolNames\`.
- 인증 주입: 컨트롤러 파라미터 \`@AuthenticationPrincipal AuthPrincipal principal\`.
- SecurityConfig: \`/api/**\` 는 authenticated, 나머지 denyAll. login/refresh/invitations/accept·GET invitations/*·actuator/health 만 permitAll. 새 엔드포인트는 모두 \`/api/\` 하위로 둘 것.
`

const SCHEMA_NOTE = `DB 스키마 원천: ${SCHEMA} 와 ${SCHEMA2} 를 반드시 읽어라. 테이블명·컬럼명·CHECK 제약값(enum)을 그대로 맞춰야 한다.`

const CONTEXT = `${RULES}

${FOUNDATION}

${SCHEMA_NOTE}

# 설계 문서 (지정한 구간만 읽어라 — 전체 93KB 읽지 말 것)
- 백엔드 클래스 목록: ${D}/03-physical-backend.md
- REST API + DTO: ${D}/02-logical-api.md
- 프론트: ${D}/02-logical-frontend.md, ${D}/03-physical-frontend.md
- 설계검증 지적: ${D}/04-design-review.md

프로젝트 루트: ${ROOT}
`

phase('구현')

const BACKEND_DOMAINS = [
  {
    label: 'BE:org+project',
    prompt: `${CONTEXT}

# 담당: org + project 도메인 (임계경로 — 이 도메인이 빌드를 가장 먼저 푼다)

**소유 경로(이 경로만 Write)**:
- ${BE}/src/main/java/kr/co/axlink/org/**
- ${BE}/src/main/java/kr/co/axlink/project/**

**읽을 설계 구간**:
- 03-physical-backend.md §2.9 org (줄 256-282), §2.10 project (줄 283-312), §3 인증(줄 559-621)
- 02-logical-api.md §2.2 orgs(168-178), §2.3 users(179-190), §2.4 projects(191-203), §2.5 assignments(204-214), §3.2(424-465), §3.3(466-544), §3.4(545-569)

**반드시 먼저 만들 것 (빌드 잠금해제)** — 현재 기반이 import 중인 미구현 클래스:
1. \`org.domain.OrgType\` enum: \`CLIENT\`, \`CONTRACTOR\` (schema ck_organization__type)
2. \`org.domain.OrgStatus\` enum: \`ACTIVE\`, \`DISABLED\`
3. \`org.domain.Role\` enum: \`SUPER_ADMIN\`, \`CLIENT\`, \`CONTRACTOR\` (schema ck_app_user__role)
4. \`org.domain.UserStatus\` enum — schema app_user 테이블 참조 (PENDING/ACTIVE/DISABLED 등 값을 스키마에서 읽어 맞출 것)
5. \`project.domain.AssignmentPermission\` enum: \`CONFIGURE_INTEGRATION\`, \`UPLOAD_DOCUMENT\`, \`READ_DASHBOARD\`
6. \`project.domain.ProjectStatus\`, \`project.domain.AssignmentStatus\` — schema project/project_assignment CHECK 참조
7. \`org.domain.AppUser\`, \`org.domain.Organization\` (record)
8. \`project.domain.Project\`, \`project.domain.ProjectAssignment\` (record)

**주의**: \`ProjectAccessResolver\` 는 이미 \`kr.co.axlink.auth.security\` 에 구현되어 있다 — 재작성 금지, 재사용. \`AssignmentPermissions\`(record, 복수형) 도 이미 \`auth.domain\` 에 있다 — 재작성 금지.

**그 뒤 구현**: org.web(OrganizationController, UserController), org.service(OrganizationService, UserService, InvitationSender — 메일 대신 log.info 로 수락URL), org.repository(OrganizationRepository, AppUserRepository), project.web(ProjectController, AssignmentController), project.service(ProjectService[UC-03: project 생성→work_product 22행→기본 dashboard 1개 단일 트랜잭션], ProjectClosureService[INV-07 종료게이트], AssignmentService, ProjectWriteGuard[INV-10], ProjectMetricsReader), project.repository(ProjectRepository, ProjectAssignmentRepository), DTO 전부.

DTO record 는 logical-api §3.2/3.3/3.4 스키마 그대로. 컨트롤러는 \`@PreAuthorize\`(역할) + ProjectAccessResolver(프로젝트·세부권한) 혼합(설계 §3.4).`,
  },
  {
    label: 'BE:integration+sync',
    prompt: `${CONTEXT}

# 담당: integration + 동기화 엔진

**소유 경로**: ${BE}/src/main/java/kr/co/axlink/integration/**

**읽을 설계 구간**:
- 03-physical-backend.md §2.11 integration(313-375), §4 동기화엔진(622-755)
- 02-logical-api.md §2.6 tool connections(215-232), §2.7 sync jobs(233-243), §3.5(570-655), §3.6(656-682)

**구현**: integration.web(ConnectionController, MappingRuleController, SyncJobController), integration.service(ConnectionService, MappingRuleService, SyncService, SyncRunner[§4.3 실행순서], SyncScheduler[§4.1]), integration.domain(ToolType, ConnectionStatus, SyncJobStatus, MappingRule, SyncJob 등 — schema tool_connection/sync_job/mapping_rule 참조), integration.port(ToolClient 포트), integration.adapter(GitHubClient, RedmineClient, 테스트용 FakeToolClient), integration.mapping(매핑규칙엔진 — 이슈타입/Tracker → 표준엔티티 분기), integration.repository, DTO.

연동 자격증명은 \`SecretCipher\` 로 암호화 저장. 동기화 잡은 \`sync_job\` 상태전이(§4.2) + 중복실행방지 + 멱등 upsert(§4.6) + Backoff 재시도(§4.7).`,
  },
  {
    label: 'BE:standard+document',
    prompt: `${CONTEXT}

# 담당: standard + document

**소유 경로**:
- ${BE}/src/main/java/kr/co/axlink/standard/**
- ${BE}/src/main/java/kr/co/axlink/document/**

**읽을 설계 구간**:
- 03-physical-backend.md §2.12 standard(376-428), §2.13 document(429-460)
- 02-logical-api.md §2.8 standard entities(244-273), §2.13 documents(321-337), §3.7(683-860), §3.11(1025-1085)

**구현 standard**: standard.web(6개 컨트롤러 — 요구사항/이슈/산출물/변경/위험/조치 등 조회·상태전이), standard.service(8개), standard.domain(21개 — work_product_type 22종 enum 은 V1__init.sql ck_work_product__type 의 22종 값과 정확히 일치, REQUIRED/ISSUE/WORK_PRODUCT/RISK/CODE_CHANGE/CHANGE_REQUEST/CORRECTION_ACTION 등 trace 엔티티타입 enum), standard.repository(9개), standard.history(entity_history 기록 — INV). 쓰기 서비스는 \`ProjectWriteGuard.assertWritable(projectId)\` 공통 호출(INV-10).

**구현 document**: document.web(DocumentController — 업로드·정형화 draft·확정·거부), document.service(5개 — 정형화), document.domain(4), document.repository(2), document.extract(4 — deepseek-v4-pro:cloud 로 비정형→정형화; \`LlmPort\` + tool calling 으로 산출물유형/요구사항 항목 추출), DTO. document 정형화는 AI 어댑터 \`fake\`/\`ollama\` 전환 대응. HWP 파싱은 미지원(한계로 명시).`,
  },
  {
    label: 'BE:semantic+widget',
    prompt: `${CONTEXT}

# 담당: semantic + dashboard(widget) — 검증 지적 HIGH-1/2/3 재발 방지 핵심

**소유 경로**:
- ${BE}/src/main/java/kr/co/axlink/semantic/**
- ${BE}/src/main/java/kr/co/axlink/dashboard/**

**읽을 설계 구간**:
- 03-physical-backend.md §2.14 semantic(461-476), §2.15 dashboard(477-490), §5 시맨틱레이어(756-839)
- 02-logical-api.md §2.9 dashboards(274-284), §2.10 widgets(285-297), §2.11 semantic catalog(298-306), §3.8(861-915), §3.9(916-959), §5 AI위젯생성(1171-1300)

**구현 semantic**: semantic.web(SemanticCatalogController — 카탈로그 조회), semantic.service(6 — CatalogLoader[§5.1], SpecValidator[§5.2 INV-24, V1~V7], SqlAssembler[§5.3 INV-26], FilterBinder[§5.4 op별 바인딩], WidgetDataAssembler[§5.3 결과→데이터]), semantic.domain(8 — measure/dimension/filter record, valueType enum: COUNT/RATE_PCT/DAYS/PCT_POINT, CATEGORY/TIME, ENUM_LIST/UUID_LIST/DATE_RANGE/MONTH_TOKEN/INT), semantic.repository(1).

**SQL 조립 규칙(핵심)**:
- measure/dimension/filter key 는 카탈로그(semantic_measure/semantic_dimension/semantic_filter 테이블)에서 조회한 식별자만 허용(화이트리스트). 임의 문자열은 식별자 위치에 삽입 불가.
- 값은 무조건 파라미터 바인딩.
- **label_expr 이 있는 dimension 은 SELECT 와 GROUP BY 양쪽에 select_expr 과 label_expr 모두 포함**(HIGH-3 재발방지).
- **requires_join 이 있는 filter 는 해당 JOIN 을 부착하고, 같은 JOIN 은 dedupe**(HIGH-1: contractor_org_id__in 필터가 dimension 없이 단독 사용되어도 JOIN 이 붙어야 함).
- \`allowedProjectIds\` 는 항상 WHERE 에 주입.

**구현 dashboard**: dashboard.web(DashboardController — 목록/생성/조회/수정/삭제/레이아웃저장; 레이아웃은 서버 DB 단일원천), dashboard.service(4), dashboard.domain(3), dashboard.repository(2), DTO.
**위젯**: widget AI 생성은 \`LlmPort.structured(..., ToolSchema)\` 로 tool calling(Prompts/ToolNames 사용). spec_json 검증(SpecValidator V1~V7). 닫힌 유니온 금지. 데이터 조회는 spec → SqlAssembler → WidgetDataAssembler 1단계.

**enum 주의**: 위젯 타입/상태 enum 은 CONSTANT_CASE (DB·프론트 일치, CRITICAL-1).`,
  },
  {
    label: 'BE:rag',
    prompt: `${CONTEXT}

# 담당: rag (Q&A + RAG)

**소유 경로**: ${BE}/src/main/java/kr/co/axlink/rag/**

**읽을 설계 구간**:
- 03-physical-backend.md §2.16 rag(491-510), §6 RAG물리(840-966)
- 02-logical-api.md §2.12 conversations/messages(307-320), §3.10(960-1024), §4 SSE(1086-1170)

**구현**: rag.web(ConversationController — 대화목록/생성, MessageController — 질의→SSE 스트리밍), rag.service(8 — ConversationService, ChunkingService[§6.1], EmbeddingService[§6.2 EmbeddingPort 사용, bge-m3 1024차원], HybridSearchService[§6.4 벡터(<=>) + FTS(plainto_tsquery('simple')) + RRF 융합], ContextAssembler[§6.5], SourceRecorder[§6.7 message_source]), rag.domain(6 — Conversation, Message, MessageSource, DocChunk, route_type enum DOCUMENT/AGGREGATE/MIXED, role enum USER/ASSISTANT), rag.repository(3 — ConversationRepository, MessageRepository, HybridSearchRepository[VectorCodec §6.3]), DTO.

**스트리밍(§6.6)**: \`LlmPort.stream(LlmRequest, Flux<LlmDelta>)\` 를 SSE 로 변환. Ollama 응답은 NDJSON 이지만 서버가 SSE 이벤트로 변환(§4.1 전송규격, §4.2 이벤트타입). 각주[n]↔출처 카드 연동(§4.3). abort 처리(§4.4). \`EmbeddingPort\`·\`LlmPort\` 포트 사용, 어댑터는 fake/ollama 자동.`,
  },
]

const FE_INFRA = {
  label: 'FE:인프라',
  prompt: `${CONTEXT}

# 담당: 프론트 공통 인프라 (화면 에이전트들이 의존하는 뼈대 — 가장 먼저 완성되어야 함)

**소유 경로(이 경로만 Write)**:
- ${FE}/src/App.tsx, ${FE}/src/main.tsx, ${FE}/src/routes.tsx
- ${FE}/src/api/client.ts, ${FE}/src/api/session.ts, ${FE}/src/api/query.ts, ${FE}/src/api/sse.ts, ${FE}/src/api/errors.ts
- ${FE}/src/lib/** (auth-context, query-provider, utils 존재), ${FE}/src/types/api.ts (존재 — 필요시 확장만)
- ${FE}/src/components/layout/** (app-layout, auth-layout, page-header, sidebar)
- ${FE}/src/components/common/** (pagination-bar 등)
- ${FE}/src/features/auth/** (login-page, invite-accept-page)

**수정 금지 경로(화면 에이전트 소유)**: features/{projects,connections,documents,dashboard,widgets,ask,admin}/**, api/{projects,assignments,connections,dashboards,widgets,semantic,qa,orgs,users,documents}.ts

**읽을 설계 구간**:
- 02-logical-frontend.md §1 라우트(26-112), §6 API클라이언트(1040-1160)
- 03-physical-frontend.md §5.1-5.3(843-907), §6 API(1042-1160), routes 표(481-540 근처)

**구현**:
1. \`api/client.ts\`: fetch 래퍼. BaseURL \`/api\`. 401 → 세션 만료 처리. JSON 요청/응답, PageResponse<T> 파싱.
2. \`api/session.ts\`: 토큰 저장(설계 §6.3 확인). login/refresh/logout.
3. \`api/query.ts\`: 서버상태 캐싱(§6.4). React Query 사용 여부는 package.json 확인 후 결정 — 미설치면 최소 캐싱 훅.
4. \`api/sse.ts\`: SSE/NDJSON 소비(§6.5, logical §4.2). fetch ReadableStream 파싱.
5. \`api/errors.ts\`: 에러 타입(§6.2).
6. \`lib/auth-context.tsx\`: AuthProvider, useAuth. \`App.tsx\`: BrowserRouter+AuthProvider+QueryProvider+Toaster+\<AppRoutes/\>.
7. \`routes.tsx\`: **모든 라우트를 미리 선언**(logical-frontend §1.2 라우트표 + physical §5.4 features 목록). 각 화면은 lazy import 하고, 화면 에이전트가 만들 파일 경로를 정확히 참조. 라우트가드(§1.3) 적용. 레이아웃 3종(§1.1) 적용.
8. \`components/layout/\`: AppLayout(사이드바 §1.4), AuthLayout, PageHeader(§5 공통). \`components/common/pagination-bar.tsx\`(PageResponse 메타).
9. \`features/auth/\`: LoginPage(§2.1), InviteAcceptPage(§2.2).

**CRITICAL-1 정정**: enum 표기는 전부 CONSTANT_CASE. 위젯 8종 타입/상태도 CONSTANT_CASE.

**중요**: routes.tsx 가 화면 파일을 import 하므로, 화면 에이전트가 만들 파일명·export명을 physical-frontend §5.4 그대로 맞춰라. 화면 파일이 아직 없어도 routes.tsx 는 import 문을 먼저 작성 — 빌드는 화면 단계 이후에 녹색이 된다.

package.json 의존성 확인(react-router-dom, @tanstack/react-query 등) — 미설치면 \`npm install\` 하지 말고 순수 React+Context 로 최소 구현도 허용.`,
}

const implementThunks = BACKEND_DOMAINS.map(d => () => agent(d.prompt, { label: d.label, phase: '구현', effort: 'high' }))
implementThunks.push(() => agent(FE_INFRA.prompt, { label: FE_INFRA.label, phase: '구현', effort: 'high' }))

const impl = await parallel(implementThunks)
const beCount = impl.slice(0, BACKEND_DOMAINS.length).filter(Boolean).length
const feInfraOk = !!impl[BACKEND_DOMAINS.length]
log(`구현단계: 백엔드 도메인 ${beCount}/${BACKEND_DOMAINS.length}, 프론트 인프라 ${feInfraOk ? '완료' : '실패'}`)

phase('화면')

const FE_SCREENS = [
  {
    label: 'FE:projects+connections+documents',
    prompt: `${CONTEXT}

# 담당: 프로젝트 생애주기 화면 3그룹

**소유 경로(이 경로만 Write)**:
- ${FE}/src/features/projects/** (project-list-page, project-create-page, project-overview-page, assignments-page)
- ${FE}/src/features/connections/** (connections-page, connections-detail-page, collection-page)
- ${FE}/src/features/documents/** (documents-page, structuring-draft-page, deliverables-page, traceability-page, changes-page, closure-page)
- ${FE}/src/api/projects.ts, ${FE}/src/api/assignments.ts, ${FE}/src/api/connections.ts, ${FE}/src/api/documents.ts

**수정 금지**: routes.tsx, App.tsx, api/{client,session,query,sse,errors}.ts, types/api.ts, features/{auth,dashboard,widgets,ask,admin}/**.

**읽을 설계 구간**:
- 02-logical-frontend.md §2.3(173-207), §2.4(208-234), §2.5(235-266), §2.6(267-299), §2.7(300-314), §2.8(315-341), §2.9(342-383), §2.10(384-410), §2.11(411-435), §2.12(436-449), §2.13(450-479)
- 03-physical-frontend.md §5.4 features/projects·connections·documents 파일표(579-631 근처), §6 API(524-533 근처)

**구현**: 각 page 컴포넌트(export 명은 physical §5.4 그대로: ProjectListPage, ProjectCreatePage, ProjectOverviewPage, AssignmentsPage, ConnectionsPage, ConnectionsDetailPage, CollectionPage, DocumentsPage, StructuringDraftPage, DeliverablesPage, TraceabilityPage, ChangesPage, ClosurePage). api/*.ts 는 logical-api §2/§3 엔드포인트·DTO 에 맞춰 \`api/client.ts\` 사용. 목업 데이터 금지 — 전부 API 호출. shadcn/ui 컴포넌트만 사용. enum CONSTANT_CASE. 주석 금지.`,
  },
  {
    label: 'FE:dashboard+widgets',
    prompt: `${CONTEXT}

# 담당: 대시보드 + 위젯 화면 (CRITICAL-1 정정 핵심)

**소유 경로**:
- ${FE}/src/features/dashboard/** (dashboard-page)
- ${FE}/src/features/widgets/** (types.ts, registry.ts, WidgetFrame, wizard 3단, 템플릿 8종 입력폼)
- ${FE}/src/api/dashboards.ts, ${FE}/src/api/widgets.ts, ${FE}/src/api/semantic.ts

**수정 금지**: routes.tsx, App.tsx, api/{client,...}.ts, types/api.ts, features/{auth,projects,connections,documents,ask,admin}/**.

**읽을 설계 구간**:
- 02-logical-frontend.md §3 위젯렌더링(492-679) — §3.2 타입(510-562), §3.3 레지스트리(563-589), §3.4 템플릿8종(590-613), §3.5 WidgetFrame(614-624), §3.6 react-grid-layout(625-656), §3.7 생성마법사(657-679)
- 03-physical-frontend.md §5.4 features/dashboard·widgets(632-672 근처)
- 02-logical-api.md §2.9 dashboards(274-284), §2.10 widgets(285-297), §2.11 semantic(298-306), §3.8(861-915), §3.9(916-959), §5 AI위젯생성(1171-1300)

**CRITICAL-1 정정(필수)**: 위젯 타입/상태 enum 은 **CONSTANT_CASE** (정확한 8종은 설계 §3.2/§5.1 에서 읽을 것). DB·Java 와 동일 표기. 소문자면 폴백 렌더되는 버그 재발.
**위젯 데이터**: spec_json 기반, 닫힌 유니온 금지, spec → 렌더러 1단계(§3.1). 레이아웃은 서버 DB 단일원천(localStorage 금지, §3.6). react-grid-layout 미설치면 package.json 확인 후 설계가 정한 방식 사용.

DashboardPage(§2.14 통합 /p/:projectId/dashboard 및 /dashboards/:dashboardId), 위젯생성마법사 3단 Dialog(§3.7, AI 생성은 api/widgets.ts generateWidget → tool calling 결과). 주석 금지, 목업 금지.`,
  },
  {
    label: 'FE:ask+admin',
    prompt: `${CONTEXT}

# 담당: AI Q&A + 관리 화면

**소유 경로**:
- ${FE}/src/features/ask/** (ask-page, useAskStream 훅)
- ${FE}/src/features/admin/** (organizations-page, users-page, audit-page)
- ${FE}/src/api/qa.ts (conversations/messages), ${FE}/src/api/orgs.ts, ${FE}/src/api/users.ts

**수정 금지**: routes.tsx, App.tsx, api/{client,session,query,sse,errors}.ts, types/api.ts, features/{auth,projects,connections,documents,dashboard,widgets}/**.

**읽을 설계 구간**:
- 02-logical-frontend.md §4 AI Q&A(680-831) — §4.1 레이아웃(682-720), §4.2 SSE(721-755), §4.3 useAskStream(756-782), §4.4 각주↔출처(783-817), §4.5 대화관리(818-831); §2.14 admin(480-491)
- 03-physical-frontend.md §5.4 features/ask·admin(673-731 근처)
- 02-logical-api.md §2.12 conversations/messages(307-320), §3.10(960-1024), §4 SSE(1086-1170); §2.2/2.3 orgs/users(168-190), §3.2(424-465)

**구현**: AskPage(/ask, /p/:projectId/ask — Sidebar+스레드 2단 §4.1), useAskStream(§4.3 — api/sse.ts 로 SSE 소비, §4.2 이벤트, §4.4 각주[n]↔출처카드, §4.5 대화목록·추천칩). OrganizationsPage, UsersPage(초대재발송 포함), AuditPage(entityType+entityId 필수조회). api/qa.ts, api/orgs.ts, api/users.ts 는 \`api/client.ts\` 사용. enum CONSTANT_CASE. 주석 금지, 목업 금지, shadcn/ui 만.`,
  },
]

const screens = await parallel(FE_SCREENS.map(s => () => agent(s.prompt, { label: s.label, phase: '화면', effort: 'high' })))
log(`화면단계: ${screens.filter(Boolean).length}/${FE_SCREENS.length} 완료`)

phase('빌드')

const BE_BUILD = `${CONTEXT}

# 담당: 백엔드 빌드 수정 (유일하게 gradle 실행)

지금 백엔드는 RED — 기반이 import 중인 org.domain.{Role,OrgType}·project.domain.AssignmentPermission 가 org+project 에이전트가 만들었을 것이고, 도메인 5갈래가 추가됐다. 컴파일 에러를 잡아 빌드를 녹색으로.

절차:
1. \`cd ${BE} && ./gradlew compileJava --console=plain 2>&1\` 로 에러 목록 파악.
2. 에러마다 원인 판단 — **프로덕션 코드의 실제 결함이면 프로덕션을 고친다** (테스트를 위해 동작 약화 금지). 도메인 에이전트가 누락한 클래스/메서드/import 가 원인이면 해당 도메인 경로에 최소 코드를 추가로 작성해 해결. 단순 타입·시그니처 불일치는 설계 문서(03-physical-backend.md, 02-logical-api.md) 기준에 맞춰 수정.
3. **소유 경로 충돌 주의**: 다른 에이전트가 안 만든 빈 자리만 채운다. 이미 작성된 클래스의 동작을 임의로 바꾸지 말고, 시그니처는 설계 기준으로 맞춘다.
4. \`./gradlew build --console=plain 2>&1\`(test 포함) 까지 녹색으로. 테스트 소스는 현재 1개(FakeAiAdapterTest)만 있으니, 신규 도메인 테스트가 없으면 컴파일만 통과하면 됨. 테스트 실패가 있으면 원인 보고.
5. 결과를 짧게 요약: 해소한 에러 수, 남은 에러(있으면), 최종 build 결과.

반복 실행 한도: 최대 5회. 그래도 안 되면 남은 에러를 그대로 보고.`

const FE_BUILD = `${CONTEXT}

# 담당: 프론트 빌드 수정 (유일하게 npm 실행)

프론트 인프라 + 화면 3그룹이 작성됐다. \`npm run build\` 와 \`vitest\` 를 녹색으로.

절차:
1. \`cd ${FE} && npm run build 2>&1\` 로 에러 파악.
2. 에러마다 수정 — **프로덕션 동작 약화 금지**. 누락된 import/타입/컴포넌트 가 원인이면 해당 소유 경로에 최소 추가 작성. routes.tsx 가 import 한 화면 파일이 없으면 화면 에이전트 경로에 빈 페이지라도 만들어 해결(단, 설계 §5.4 파일명·export명 준수).
3. \`npx vitest run 2>&1\` 도 통과.
4. **CRITICAL-1 재확인**: 위젯 enum 이 CONSTANT_CASE 인지 빌드/타입에서 확인.
5. 결과 요약: 해소 에러 수, 남은 에러, 최종 build/test 결과.

반복 한도: 최대 5회.`

const builds = await parallel([
  () => agent(BE_BUILD, { label: 'BE:빌드', phase: '빌드', effort: 'high' }),
  () => agent(FE_BUILD, { label: 'FE:빌드', phase: '빌드', effort: 'high' }),
])

return {
  backendDomains: beCount,
  feInfra: feInfraOk,
  screens: screens.filter(Boolean).length,
  beBuild: builds[0],
  feBuild: builds[1],
}