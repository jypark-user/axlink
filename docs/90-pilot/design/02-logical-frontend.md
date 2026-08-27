# AX-Link 논리 설계 — 프론트엔드 화면·모듈 설계

> **2026-08-21 범위 확정**: 연동 도구는 형상관리 **GitHub** · 프로젝트 관리 **Redmine** 2종으로 확정했다.
> 이 문서의 Jira · GitLab · Notion 관련 서술은 그 시점 이전 기록이며 더 이상 유효하지 않다.
> 현재 범위는 `docs/AX-Link-PRD.md` §1.4 와 `docs/design/02-logical-datamodel.md` §3.5 를 따른다.


| 항목 | 내용 |
| --- | --- |
| 문서 ID | `design/02-logical-frontend` |
| 버전 | v1.0 (2026-08-20) |
| 상위 문서 | `docs/AX-Link-PRD.md` §6, `design/01-conceptual-domain.md`, `design/01-conceptual-architecture.md` |
| 범위 | 라우트 · 화면 · 위젯 렌더링 · Q&A · 디렉터리 · API 클라이언트 · 디자인 토큰 |
| 대상 | React 19 + Vite + TypeScript + Tailwind CSS v4 + shadcn/ui + react-router v7 |

## 0. 이 문서가 고정하는 전제

| 전제 | 값 | 근거 |
| --- | --- | --- |
| 컴포넌트 | shadcn/ui 전용. 없으면 radix 프리미티브 + shadcn 스타일로 `components/ui/` 에 추가 | ADR-009 |
| 기능 라이브러리 예외 | `react-grid-layout`, `recharts` 2개만. 표시 계층은 shadcn `Card`/`Chart` 로 감싼다 | ADR-009 |
| 서버 상태 캐싱 | **외부 라이브러리 추가 없음.** `api/query.ts` 의 `useApiQuery` / `useApiMutation` 훅으로 처리한다. `01-conceptual-architecture.md` §2.2 표의 "TanStack Query 훅" 표기는 본 문서에서 자체 훅으로 확정한다 | 의존성 최소화 |
| 라우팅 | `react-router` v7 (`createBrowserRouter`), 데이터 로더 미사용. 데이터는 컴포넌트 훅에서만 가져온다 | 수정 지점 단일화 |
| 레이아웃 저장소 | 서버 `dashboard.layout_json` 만. `localStorage`/`sessionStorage` 에 레이아웃·위젯 상태를 쓰지 않는다 | ADR-007 / INV-27 |
| 목업 데이터 | 금지. `src` 하위에 `mocks/`, `fixtures/`, 하드코딩 배열 상수(데이터성)를 두지 않는다 | PRD §6.1.1 |
| 위젯 | `spec_json` → 렌더러 1단계. 닫힌 유니온 타입 금지, `Record<string, WidgetRenderer>` 맵 | ADR-006 / INV-28 |
| 코드 스타일 | named export 전용, `@/` 별칭, 들여쓰기 2칸, 작은따옴표, `any` 금지, 주석 금지 | 공통 컨텍스트 |

---

## 1. 라우트 트리

### 1.1 레이아웃 3종

| 레이아웃 | 파일 | 구성 | 적용 |
| --- | --- | --- | --- |
| `AuthLayout` | `components/layout/AuthLayout.tsx` | 앱셸 없음. 중앙 정렬 `Card` 1개 | 로그인·초대 수락 |
| `AppShell` | `components/layout/AppShell.tsx` | `SidebarProvider` + `AppSidebar` + `AppHeader`(Breadcrumb·UserMenu) + `<Outlet/>` + `Toaster` | 그 외 전 화면 |
| `ProjectLayout` | `components/layout/ProjectLayout.tsx` | `AppShell` 내부 중첩. 프로젝트 헤더(이름·기간·상태 Badge) + `ProjectNav`(Tabs) + `<Outlet/>` | `/p/:projectId/*` |

`AskLayout` 은 별도로 두지 않는다. `/ask` 계열은 `AppShell` 안에서 `h-[calc(100svh-var(--header-h))]` 풀블리드 컨테이너로 렌더한다(패턴 발명 금지, 셸은 하나).

### 1.2 라우트 표

`R` = 읽기 가능, `W` = 쓰기 가능, `—` = 접근 불가(403 화면).

| 경로 | 화면명 | 파일 | 레이아웃 | SUPER_ADMIN | CLIENT | CONTRACTOR | 데이터 의존 API |
| --- | --- | --- | --- | :-: | :-: | :-: | --- |
| `/login` | 로그인 | `features/auth/LoginPage.tsx` | Auth | 공개 | 공개 | 공개 | `POST /api/auth/login` |
| `/invite/accept` | 초대 수락·비밀번호 설정 | `features/auth/AcceptInvitePage.tsx` | Auth | 공개 | 공개 | 공개 | `GET /api/auth/invitations/{token}`, `POST /api/auth/invitations/{token}/accept` |
| `/` | → `/projects` 리다이렉트 | — | — | — | — | — | — |
| `/projects` | 프로젝트 목록 | `features/projects/ProjectListPage.tsx` | AppShell | R | W | R | `GET /api/projects?scope=mine` |
| `/projects/new` | 프로젝트 생성 | `features/projects/ProjectListPage.tsx` + `ProjectCreateDialog` | AppShell | — | W | — | `POST /api/projects` |
| `/p/:projectId` | 프로젝트 개요 | `features/projects/ProjectOverviewPage.tsx` | Project | R | R | R | `GET /api/projects/{id}`, `GET /api/projects/{id}/summary` |
| `/p/:projectId/dashboard` | 대시보드(기본) | `features/dashboard/DashboardPage.tsx` | Project | — | W | R(권한 토글) | `GET /api/projects/{id}/dashboards`, `GET /api/dashboards/{did}` |
| `/p/:projectId/dashboard/:dashboardId` | 대시보드(지정) | 동일 | Project | — | W | R(권한 토글) | `GET /api/dashboards/{did}`, `GET /api/widgets/{wid}/data` |
| `/p/:projectId/assignments` | 용역사 할당 | `features/assignments/AssignmentsPage.tsx` | Project | R | W | — | `GET /api/projects/{id}/assignments`, `GET /api/organizations?type=CONTRACTOR`, `GET /api/organizations/{oid}/users` |
| `/p/:projectId/connections` | 연동 관리 | `features/connections/ConnectionsPage.tsx` | Project | R | R | W(연동설정 토글) | `GET /api/projects/{id}/connections`, `POST /api/connections/test` |
| `/p/:projectId/connections/:connectionId` | 매핑 규칙 편집 | `features/connections/MappingRulesPage.tsx` | Project | R | R | W(연동설정 토글) | `GET /api/connections/{cid}/mapping-rules` |
| `/p/:projectId/collection` | 동기화 현황 | `features/collection/SyncStatusPage.tsx` | Project | R | R | R | `GET /api/projects/{id}/sync-jobs`, `POST /api/sync-jobs/{jid}/retry` |
| `/p/:projectId/documents` | 문서 업로드·정형화 | `features/documents/DocumentsPage.tsx` | Project | — | W | W(업로드 토글) | `GET /api/projects/{id}/documents`, `POST /api/projects/{id}/documents`, `GET /api/documents/{did}/draft` |
| `/p/:projectId/deliverables` | 산출물 22종 점검표 | `features/deliverables/DeliverableChecklistPage.tsx` | Project | R | W(승인) | R | `GET /api/projects/{id}/work-products` |
| `/p/:projectId/deliverables/:type` | 산출물 상세 | `DeliverableDetailSheet`(같은 페이지 위 Sheet) | Project | R | W | R | `GET /api/projects/{id}/work-products/{type}` |
| `/p/:projectId/traceability` | 요구사항 추적 | `features/traceability/TraceabilityPage.tsx` | Project | R | R | R | `GET /api/projects/{id}/traceability` |
| `/p/:projectId/changes` | 변경·시정 | `features/changes/ChangesPage.tsx` | Project | R | W | R | `GET /api/projects/{id}/change-requests`, `GET /api/projects/{id}/correction-actions` |
| `/p/:projectId/closure` | 검수·종료 | `features/closure/ClosurePage.tsx` | Project | R | W | R | `GET /api/projects/{id}/acceptance-record`, `POST /api/projects/{id}/acceptance-record`, `POST /api/projects/{id}/close` |
| `/p/:projectId/ask` | AI Q&A (프로젝트 고정 범위) | `features/ask/AskPage.tsx` | Project | — | W | W | `/api/conversations*`, `POST /api/qna/messages` |
| `/ask` | AI Q&A (전체 범위) | `features/ask/AskPage.tsx` | AppShell | — | W | W | 동일 |
| `/ask/:conversationId` | AI Q&A 대화 | 동일 | AppShell | — | W | W | `GET /api/conversations/{cid}/messages` |
| `/admin/organizations` | 조직 관리 | `features/admin/OrganizationsPage.tsx` | AppShell | W | — | — | `GET/POST /api/organizations` |
| `/admin/users` | 계정·역할 관리 | `features/admin/UsersPage.tsx` | AppShell | W | — | — | `GET/POST /api/users`, `POST /api/users/{uid}/invite` |
| `/admin/audit` | 감사 로그 | `features/admin/AuditLogPage.tsx` | AppShell | W | R(자사) | — | `GET /api/audit-entries` |
| `/403` | 접근 거부 | `components/common/ForbiddenPage.tsx` | AppShell | 공통 | 공통 | 공통 | — |
| `*` | 없는 화면 | `components/common/NotFoundPage.tsx` | AppShell | 공통 | 공통 | 공통 | — |

### 1.3 라우트 가드

```tsx
<Route element={<RequireAuth />}>
  <Route element={<AppShell />}>
    <Route path="projects" element={<ProjectListPage />} />
    <Route path="projects/new" element={<ProjectListPage />} />
    <Route element={<RequireRole roles={['SUPER_ADMIN']} />}>
      <Route path="admin/organizations" element={<OrganizationsPage />} />
    </Route>
    <Route path="p/:projectId" element={<ProjectLayout />}>
      <Route index element={<ProjectOverviewPage />} />
      <Route element={<RequireRole roles={['CLIENT']} />}>
        <Route path="assignments" element={<AssignmentsPage />} />
      </Route>
    </Route>
  </Route>
</Route>
```

| 가드 | 파일 | 판정 | 실패 시 |
| --- | --- | --- | --- |
| `RequireAuth` | `components/layout/RequireAuth.tsx` | 세션 부트스트랩(`useSession`) 완료 + 인증됨 | `/login?next={pathname}` |
| `RequireRole` | `components/layout/RequireRole.tsx` | `session.role ∈ roles` | `/403` |
| 프로젝트 접근 | `ProjectLayout` | `GET /api/projects/{id}` 응답 코드 | `PROJECT_ACCESS_DENIED` → `/403` |
| 세부 권한 | 화면 내부 | `project.myPermissions.{canConfigureIntegration,canUploadDocument,canReadDashboard}` | 액션 버튼 `disabled` + 사유 Tooltip |

**클라이언트 가드는 UX용이다.** 실제 권한은 서버가 판정한다(INV-04). 프론트는 서버 403 응답을 신뢰 원천으로 삼고 화면을 전환한다.

### 1.4 사이드바 내비게이션 구성

| 그룹 | 항목 | 표시 조건 |
| --- | --- | --- |
| (상단) | 프로젝트 | 전 역할 |
| (상단) | AI Q&A | CLIENT, CONTRACTOR |
| 관리 | 조직 / 계정 / 감사 로그 | SUPER_ADMIN (감사 로그는 CLIENT 도 자사 한정) |
| (하단) | 계정 DropdownMenu(이름·조직·역할·로그아웃), 테마 토글 | 전 역할 |

프로젝트 내부 탭(`ProjectNav`)은 사이드바가 아니라 `ProjectLayout` 상단 `Tabs` 로 둔다: 개요 / 대시보드 / 산출물 / 추적 / 변경·시정 / 연동 / 동기화 / 문서 / 할당 / 검수·종료 / Q&A. 권한 없는 탭은 렌더하지 않는다.

---

## 2. 화면별 상세 설계

공통 규칙:

| 상태 | 렌더 방식 | 컴포넌트 |
| --- | --- | --- |
| 로딩 | 화면 골격 유지 + `Skeleton`. 스피너 전면 덮기 금지 | `Skeleton` |
| 빈값 | 데이터 기준 문구 1줄 + (권한 있으면) 1차 액션 버튼. 안내·배려 문구 금지 | `components/common/EmptyState.tsx` |
| 에러 | `Alert variant="destructive"` + 서버 `ErrorResponse.code`·`message` 원문 + 재시도 버튼 | `Alert` |
| 3상태 분기 | 모든 화면이 동일 컴포넌트로 감싼다 | `components/common/DataState.tsx` |

```tsx
<DataState query={projects} skeleton={<ProjectCardSkeleton count={6} />} empty={{ text: '프로젝트 0건', action: canCreate ? createAction : null }}>
  {(rows) => <ProjectGrid rows={rows} />}
</DataState>
```

---

### 2.1 `/login` — 로그인

**목적**: 이메일·비밀번호로 세션 발급(UC-02).

```
┌───────────────────────────────────────┐
│                                       │
│        ┌───────────────────────┐      │
│        │  AX-Link              │      │
│        │  ───────────────────  │      │
│        │  이메일   [__________]│      │
│        │  비밀번호 [__________]│      │
│        │  [ Alert: 로그인 실패 ]│      │
│        │  [      로그인       ]│      │
│        └───────────────────────┘      │
│                                       │
└───────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Card`, `CardHeader/Content/Footer`, `Form`(react-hook-form + zod), `Input`, `Label`, `Button`, `Alert` |
| 상태 | 로딩: 제출 버튼 `disabled` + 텍스트 유지 / 에러: `Alert` 에 `AUTH_INVALID_CREDENTIALS` 메시지 / 빈값 없음 |
| API | `POST /api/auth/login {email, password}` → `{accessToken, expiresIn, user}` |
| 역할 차이 | 없음. 로그인 후 역할별 기본 경로: SUPER_ADMIN → `/admin/organizations`, 그 외 → `/projects`. `?next=` 가 있으면 우선 |

---

### 2.2 `/invite/accept` — 초대 수락

**목적**: SUPER_ADMIN 이 만든 계정의 최초 비밀번호 설정(UC-01 ④).

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Card`, `Form`, `Input(type=password)`, `Button`, `Alert` |
| 상태 | 토큰 검증 로딩 `Skeleton` / 만료·사용됨 → `Alert` + 로그인 이동 버튼 |
| API | `GET /api/auth/invitations/{token}` → `{email, orgName, role}` · `POST .../accept {password}` |
| 검증 | zod: 8자 이상, 영문·숫자 포함, 확인란 일치 |

---

### 2.3 `/projects` · `/projects/new` — 프로젝트 목록 / 생성

**목적**: ProjectScope 로 필터된 프로젝트 카드 목록(UC-05)과 생성(UC-03).

`/projects/new` 는 별도 페이지가 아니라 **같은 페이지 위의 라우트 구동 Dialog** 다. 열림 판정은 `useMatch('/projects/new')`, 닫으면 `navigate('/projects')`.

```
┌ AppShell ───────────────────────────────────────────────┐
│ 프로젝트                              [+ 프로젝트 생성]  │
│ [ 검색 Input ] [상태 Select] [정렬 Select]              │
│ ┌─ Card ────────┐ ┌─ Card ────────┐ ┌─ Card ────────┐  │
│ │ 사업명        │ │               │ │               │  │
│ │ [active][SI.4]│ │               │ │               │  │
│ │ 2026-03-02 ~  │ │               │ │               │  │
│ │ 2026-11-30    │ │               │ │               │  │
│ │ 산출물 12/22  │ │               │ │               │  │
│ │ ▓▓▓▓▓▓░░░ 55% │ │               │ │               │  │
│ │ 열린 조치 3건 │ │               │ │               │  │
│ └───────────────┘ └───────────────┘ └───────────────┘  │
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui (목록) | `Card`, `Badge`, `Progress`, `Skeleton`, `Input`, `Select`, `Button` |
| shadcn/ui (생성) | `Dialog`, `Form`, `Input`, `Textarea`, `Calendar` + `Popover`(착수일·마감일), `Button`, `Alert` |
| 카드 표시값 | `name`, `status` Badge, `currentSiPhase` Badge, `startDate ~ endDate`(항상 한 쌍), 승인 산출물 `n/22` + `Progress`, 열린 시정조치 건수 |
| 상태 | 로딩: 카드 6개 Skeleton / 빈값: "프로젝트 0건" + CLIENT 만 생성 버튼 / 에러: Alert |
| 생성 검증 | zod — `name` 필수(1~120), `startDate`·`endDate` 필수, `endDate >= startDate`(INV-08), `description` 필수(INV-09) |
| API | `GET /api/projects?scope=mine&q=&status=` · `POST /api/projects {name,startDate,endDate,description}` |
| 성공 후 | `invalidate('/api/projects')` → `navigate('/p/{id}')`, `Sonner` 토스트 1줄 |
| 역할 차이 | 생성 버튼·Dialog 라우트는 CLIENT 만. CONTRACTOR 는 할당된 프로젝트만 목록에 나온다(서버 필터) |

---

### 2.4 `/p/:projectId` — 프로젝트 개요

**목적**: 프로젝트 단일 화면 요약. 위젯 시스템을 쓰지 않는 **고정 화면**이다(대시보드와 역할 분리).

```
┌ ProjectLayout ──────────────────────────────────────────┐
│ 사업명   [active] 2026-03-02 ~ 2026-11-30    [종료 요청] │
│ [개요][대시보드][산출물][추적][변경·시정][연동][동기화]…│
│ ┌ Card 요구사항 ─┐┌ Card 산출물 ─┐┌ Card 이슈 ─┐┌ 리스크┐│
│ │ 이행률 62%     ││ 승인 12/22   ││ 열린 34건  ││ 5건   ││
│ └────────────────┘└──────────────┘└────────────┘└───────┘│
│ ┌ Card 최근 동기화 ───────────┐┌ Card 열린 시정조치 ────┐│
│ │ Jira  2분 전  성공  128건   ││ Table (기한·담당·상태) ││
│ │ GitLab 12분 전 실패 [재시도]││                        ││
│ └─────────────────────────────┘└────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Card`, `Badge`, `Progress`, `Table`, `Button`, `Separator`, `Tabs`(ProjectNav), `Skeleton` |
| API | `GET /api/projects/{id}` (헤더·권한), `GET /api/projects/{id}/summary` (KPI 4종 + 최근 동기화 3건 + 열린 시정조치 5건) |
| 상태 | 부분 로딩 허용. KPI 카드 각각 Skeleton |
| 역할 차이 | `[종료 요청]` 은 CLIENT 만 노출. CONTRACTOR 는 KPI·동기화만, 할당 정보는 표시하지 않음 |

---

### 2.5 `/p/:projectId/assignments` — 용역사 할당

**목적**: 용역사 조직·계정 할당과 세부 권한 토글 3종(UC-04, PRJ-003/004).

```
┌─────────────────────────────────────────────────────────┐
│ 용역사 할당                            [+ 용역사 추가]   │
│ ┌ Table ───────────────────────────────────────────────┐│
│ │ 조직     계정        연동설정 문서업로드 대시보드 [해제]││
│ │ ○○소프트 kim@..      [ on ]  [ on ]    [ off ]  [해제]││
│ └──────────────────────────────────────────────────────┘│
│                                                          │
│ [+ 용역사 추가] → Sheet(우측)                            │
│   ┌ Sheet ─────────────────────┐                        │
│   │ 용역사 조직 [Command 검색] │                        │
│   │ 계정 목록  [x] kim [ ] lee │                        │
│   │ 권한 Switch 3종            │                        │
│   │ [취소] [할당]              │                        │
│   └────────────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Table`, `Sheet`, `Command`(조직·계정 검색), `Checkbox`, `Switch`, `Button`, `AlertDialog`(해제 확인), `Badge` |
| 상태 | 빈값: "할당된 용역사 0건" + 추가 버튼 / 토글 저장 실패 시 이전 값 롤백 + `Sonner` 에러 |
| API | `GET /api/projects/{id}/assignments`, `POST /api/projects/{id}/assignments {contractorOrgId,userIds[],permissions}`, `PATCH /api/assignments/{aid}/permissions`, `DELETE /api/projects/{id}/assignments/{aid}` |
| 저장 타이밍 | Switch 는 즉시 저장(낙관적 갱신 + 실패 롤백). Sheet 는 명시적 [할당] 클릭 |
| 역할 차이 | CLIENT 전용 화면. SUPER_ADMIN 은 읽기만(토글 `disabled`) |

---

### 2.6 `/p/:projectId/connections` — 연동 관리

**목적**: Jira·GitLab 연결 등록·테스트·상태 관리(UC-06, INT-001~003).

```
┌─────────────────────────────────────────────────────────┐
│ 연동 관리                                  [+ 연결 추가] │
│ ┌ Card ─ Jira ─────────────────┐ ┌ Card ─ GitLab ──────┐│
│ │ [active] jira.acme.com       │ │ [failed]            ││
│ │ 대상 PROJ                    │ │ 대상 group/app      ││
│ │ 최근 동기화 2분 전 · 128건   │ │ 오류: 401 Unauthor… ││
│ │ [연결 테스트][매핑규칙][수정]│ │ [연결 테스트][수정] ││
│ └──────────────────────────────┘ └─────────────────────┘│
│                                                          │
│ [+ 연결 추가] → Dialog                                   │
│   [Tabs: Jira | GitLab]                                  │
│   베이스 URL [__] 인증 [••••] 대상 리소스 [__]           │
│   [연결 테스트] → Alert(성공/도구 원문 오류)             │
│   [취소] [저장]  ← 테스트 성공 전 disabled               │
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Card`, `Badge`, `Dialog`, `Tabs`(도구별), `Form`, `Input`(인증은 `type=password`), `Select`, `Button`, `Alert`, `AlertDialog`(삭제), `Tooltip` |
| 인증정보 표시 | 서버는 마스킹 값(`****abcd`)만 반환(INV-06). 수정 화면에서 빈칸이면 기존 값 유지, 입력하면 교체 |
| 검증 | 저장 버튼은 `testStatus === 'passed'` 일 때만 활성(INV-19) |
| 상태 | 테스트 진행 중: 버튼 로딩 / 실패: `Alert` 에 도구 API 원문 메시지 그대로(INT-002) |
| API | `GET /api/projects/{id}/connections`, `POST /api/connections/test {tool,baseUrl,auth,targetResource}`, `POST /api/projects/{id}/connections`, `PATCH /api/connections/{cid}`, `DELETE /api/connections/{cid}` |
| 역할 차이 | CONTRACTOR + `canConfigureIntegration` 만 쓰기. CLIENT·SUPER_ADMIN 은 카드 조회만(버튼 `disabled` + Tooltip "발주사는 조회만 가능") |

---

### 2.7 `/p/:projectId/connections/:connectionId` — 매핑 규칙 편집

**목적**: 도구 개체 → 표준 개념 매핑을 데이터로 편집(UC-09, P2 원칙).

| 항목 | 내용 |
| --- | --- |
| 구조 | `Table` 한 개. 행 = 규칙, 열 = `source_kind`(issuetype/objectKind) · `source_value` · 표준 개념 `Select` · 상태 매핑 `Select` × 3 · 활성 `Switch` · 삭제 |
| shadcn/ui | `Table`, `Select`, `Switch`, `Button`, `Input`, `AlertDialog`(즉시 백필 확인), `Badge`(`unmapped` 건수) |
| 표준 개념 옵션 | `GET /api/semantic/promotion-targets` 로 받는다. 프론트에 하드코딩하지 않는다 |
| 저장 | 하단 고정 바 `[취소] [저장]`. 저장 후 AlertDialog "다음 폴링부터 적용 / 지금 전체 백필" 선택 |
| API | `GET /api/connections/{cid}/mapping-rules`, `PUT /api/connections/{cid}/mapping-rules`, `POST /api/connections/{cid}/backfill` |
| 상태 | 미매핑 도구 개체값은 상단 `Alert` 에 상위 10건 + 건수 표시(INV-21) |

---

### 2.8 `/p/:projectId/collection` — 동기화 현황

**목적**: sync_job 목록·실패 원인·재시도(UC-10, INT-004).

```
┌─────────────────────────────────────────────────────────┐
│ 동기화 현황     [연결 Select][종류 Select][상태 Select]  │
│ ┌ Table ───────────────────────────────────────────────┐│
│ │ 연결   종류   상태     시작        소요  적재  동작   ││
│ │ Jira   POLL   [성공]   14:32:10    2.1s  128   —      ││
│ │ GitLab BACKFILL[실패]① 13:02:44    9.8s  0    [재시도]││
│ └──────────────────────────────────────────────────────┘│
│ ① Tooltip: 도구 응답 원문 오류 메시지                    │
│ [Pagination]                                             │
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Table`, `Badge`(queued/running/succeeded/failed/cancelled), `Tooltip`(오류 원문), `Button`(재시도), `Select`(필터), `Pagination`, `Skeleton` |
| 자동 갱신 | `running` 상태 행이 1건 이상이면 `useApiQuery` 의 `refetchInterval: 5000`. 없으면 폴링 중단 |
| 상태 | 빈값: "동기화 이력 0건" / 재시도 실패 시 `Sonner` 에러 |
| API | `GET /api/projects/{id}/sync-jobs?connectionId=&status=&page=`, `POST /api/sync-jobs/{jid}/retry` |
| 역할 차이 | CONTRACTOR 는 자사 연결분만(서버 필터). 재시도는 `canConfigureIntegration` 필요 |

---

### 2.9 `/p/:projectId/documents` — 문서 업로드·정형화 확정

**목적**: 업로드 → 텍스트 추출 → `deepseek-v4-pro:cloud` 정형화 초안 → **사용자 확정** → 표준 적재(UC-11, INT-006, INV-33).

```
┌─────────────────────────────────────────────────────────┐
│ 문서                                                     │
│ ┌ 드롭존(커스텀: div + input[type=file]) ───────────────┐│
│ │  HWP · HWPX · DOCX · XLSX · PDF   최대 50MB           ││
│ │  [파일 선택]                                          ││
│ └───────────────────────────────────────────────────────┘│
│ 업로드 중: 파일명 ▓▓▓▓▓░░ 62%  (Progress)               │
│ ┌ Table ───────────────────────────────────────────────┐│
│ │ 파일명  상태          추정 유형        동작           ││
│ │ 요구.hwp [structured] [REQUIREMENTS_SPEC] [확정하기]  ││
│ │ 설계.pdf [extracted]  —                  (처리 중)    ││
│ └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘

[확정하기] → Dialog
┌ 정형화 확정 ──────────────────────────────────────────┐
│ 산출물 유형 [Select: 22종]      ← AI 추정값 Badge 병기 │
│ 제목 [__________]  버전 [____]  작성일 [Calendar]      │
│ 추출된 요구사항 (12건)                                 │
│ ┌ Table ─────────────────────────────────────────────┐ │
│ │ [x] 코드   제목            우선순위 Select          │ │
│ └────────────────────────────────────────────────────┘ │
│ [반려] [수동 지정] [확정 적재]                         │
└────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Table`, `Progress`, `Badge`, `Dialog`, `Select`, `Input`, `Calendar`+`Popover`, `Checkbox`, `Button`, `Alert`, `Skeleton` |
| 드롭존 | shadcn 카탈로그에 없다. `components/ui/dropzone.tsx` 에 **커스텀 추가** — radix 프리미티브 불필요(네이티브 `input[type=file]` + `onDragOver/onDrop`), 스타일은 shadcn `border-dashed`·`bg-muted/50` 규격 준수 |
| 상태 | `uploaded` → `extracted` → `structured` 는 3초 폴링으로 갱신. 정형화 실패(`AI_UNAVAILABLE`, `WORK_PRODUCT_TYPE_REJECTED`) 시 행에 `Alert` 대신 Badge + Tooltip, [수동 지정] 버튼으로 전환 |
| 확정 검증 | 유형 Select 옵션은 `@/standard/workProductTypes` 22종 단일 정의(INV-11/18) |
| API | `POST /api/projects/{id}/documents`(multipart), `GET /api/projects/{id}/documents`, `GET /api/documents/{did}/draft`, `POST /api/documents/{did}/confirm {type,title,version,issuedAt,requirements[]}`, `POST /api/documents/{did}/reject` |
| 역할 차이 | CLIENT 는 항상 가능. CONTRACTOR 는 `canUploadDocument` 필요. 없으면 드롭존을 `disabled` 로 렌더하고 사유 Tooltip |

---

### 2.10 `/p/:projectId/deliverables` — 산출물 22종 점검표

**목적**: 22종 × 적용대상 × 상태 상시 조회(UC-12, STD-001). 행은 항상 22개다(INV-12).

```
┌─────────────────────────────────────────────────────────┐
│ 산출물 점검표      승인 12/22  ▓▓▓▓▓░░░░  [상태 Select] │
│ ┌ Table (고정 헤더) ───────────────────────────────────┐│
│ │ #  구분  산출물          활동   버전  상태     갱신  ││
│ │ 1  PM    과업지시서      PM.1   v1.2  [승인]   03-04 ││
│ │ 2  PM    사업수행계획서  PM.1   —     [없음]   —     ││
│ │ …                                                     ││
│ │ 22 각활동 확인 결과      —      —     [제출]   08-11 ││
│ └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Table`, `Badge`(none/draft/submitted/approved/rejected), `Progress`, `Select`, `Sheet`(상세), `Button`, `AlertDialog`(승인·반려) |
| 상태 표기 | `none` = "없음" `Badge variant="outline"`. 행이 사라지는 표현 금지 |
| 상세 Sheet | 라우트 `/deliverables/:type` 로 열고 닫으면 목록으로 복귀. 내용: 버전 이력 `Table`, 파일 링크/외부 딥링크, 승인 이력(`entity_history`) |
| API | `GET /api/projects/{id}/work-products`, `GET /api/projects/{id}/work-products/{type}`, `POST /api/work-products/{wid}/approve`, `POST /api/work-products/{wid}/reject` |
| 역할 차이 | 승인·반려 버튼은 CLIENT 전용. CONTRACTOR 는 제출(`draft → submitted`)만 |

---

### 2.11 `/p/:projectId/traceability` — 요구사항 추적

**목적**: 요구사항 ↔ 설계 ↔ 구현(MR) ↔ 시험 추적표와 끊김 하이라이트(UC-13, STD-002).

```
┌─────────────────────────────────────────────────────────┐
│ 요구사항 추적   추적률 74%  [검색][상태][끊김만 Switch] │
│ ┌ Table (고정 헤더, 가로 스크롤) ──────────────────────┐│
│ │ 코드    요구사항        상태      설계  구현  시험   ││
│ │ REQ-001 로그인 SSO      [verified] ✓②   ✓③   ✓④    ││
│ │ REQ-002 권한 매트릭스   [defined]  —!   —!   —!     ││
│ └──────────────────────────────────────────────────────┘│
│ ! = 끊김 Badge(destructive) · ✓ = HoverCard 로 링크 목록 │
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Table`(`sticky top-0` 헤더), `Badge`, `HoverCard`(링크 상세 — 대상 제목·딥링크), `Switch`(끊김만), `Input`(검색), `Tooltip`, `Skeleton` |
| 끊김 판정 | 서버가 `traceGaps: ('designs'|'implements'|'tests')[]` 로 내려준다. 프론트에서 계산하지 않는다 |
| API | `GET /api/projects/{id}/traceability?onlyGaps=&q=` |
| 역할 차이 | 없음(조회 전용) |

---

### 2.12 `/p/:projectId/changes` — 변경·시정

**목적**: ChangeRequest + CorrectionAction 목록·상태 전이(STD-003).

| 항목 | 내용 |
| --- | --- |
| 구조 | `Tabs`: [변경요청] [시정조치] 2탭, 각 탭 `Table` |
| shadcn/ui | `Tabs`, `Table`, `Badge`, `Select`(상태 전이), `Dialog`(등록/수정), `Form`, `Calendar`+`Popover`(기한), `AlertDialog`(상태 전이 확정), `Pagination` |
| 강조 | `overdue` 행은 `text-destructive` + Badge. 정렬 기본 = 기한 오름차순 |
| API | `GET/POST /api/projects/{id}/change-requests`, `PATCH /api/change-requests/{cid}`, `GET/POST /api/projects/{id}/correction-actions`, `PATCH /api/correction-actions/{aid}` |
| 역할 차이 | 상태 전이는 CLIENT. CONTRACTOR 는 자기 담당 시정조치의 `open → done` 만 |

---

### 2.13 `/p/:projectId/closure` — 검수·종료

**목적**: 검수확인서 등록 후 종료 게이트 통과(UC-18, STD-004, INV-07).

```
┌─────────────────────────────────────────────────────────┐
│ 검수·종료                                                │
│ ┌ Card 종료 게이트 ────────────────────────────────────┐│
│ │ ✓ 검수확인서 등록                                     ││
│ │ ✗ 필수 산출물 승인      12/22                         ││
│ │ ✓ 열린 시정조치 0건                                   ││
│ │                              [프로젝트 종료] disabled ││
│ └───────────────────────────────────────────────────────┘│
│ ┌ Card 검수확인서 ─────────────────────────────────────┐│
│ │ 인수자[__] 인수일[Calendar] 조건[Textarea] 문서[파일] ││
│ │                                        [검수확인 등록]││
│ └───────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Card`, `Form`, `Input`, `Textarea`, `Calendar`+`Popover`, `Button`, `AlertDialog`(종료 확정 — 파괴적 액션 필수), `Badge`, `Alert` |
| 게이트 판정 | 서버 `GET /api/projects/{id}/closure-gate` → `{items:[{key,label,passed,detail}], closable}`. 프론트는 `closable` 만 보고 버튼 활성 |
| 상태 | 종료 성공 → `Project.status = closed`, 화면 전체 읽기 전용 전환(INV-10), 모든 쓰기 버튼 `disabled` |
| API | `GET /api/projects/{id}/acceptance-record`, `POST /api/projects/{id}/acceptance-record`, `GET /api/projects/{id}/closure-gate`, `POST /api/projects/{id}/close` |
| 역할 차이 | CLIENT 전용 쓰기. CONTRACTOR 는 게이트 카드만 조회 |

---

### 2.14 `/admin/*` — 관리 화면

| 화면 | 구성 | shadcn/ui | API |
| --- | --- | --- | --- |
| 조직 관리 | `Table`(조직명·유형 Badge·사업자번호·계정 수) + `Dialog` 등록/수정 | `Table`, `Dialog`, `Form`, `Input`, `Select`, `Badge`, `AlertDialog` | `GET/POST /api/organizations`, `PATCH /api/organizations/{oid}` |
| 계정·역할 | `Table`(이메일·이름·조직·역할 Badge·상태) + `Dialog` 생성 + [초대 재발송] | `Table`, `Dialog`, `Form`, `Input`, `Select`(조직·역할), `Badge`, `Button`, `AlertDialog`(비활성화) | `GET/POST /api/users`, `POST /api/users/{uid}/invite`, `PATCH /api/users/{uid}/status` |
| 감사 로그 | `Table`(시각·행위자·대상·필드·이전→이후) + 필터(`Select` 엔티티 유형, `Calendar` 기간) + `Pagination` | `Table`, `Select`, `Calendar`+`Popover`, `Pagination`, `Badge` | `GET /api/audit-entries?entityType=&from=&to=&page=` |

CLIENT 는 `/admin/audit` 만 접근 가능하며 서버가 자사 프로젝트로 필터한다.

---

## 3. 대시보드 위젯 렌더링 설계

### 3.1 렌더 경로 (1단계)

```
GET /api/dashboards/{id}       → { layout: LayoutMap, widgets: Widget[] }
GET /api/widgets/{wid}/data    → WidgetDataset
                                        │
Widget.spec ──────────────────┐         │
                              ▼         ▼
        widgetRenderers[spec.template] ?? UnsupportedWidget
                              │
                              ▼
                        <Renderer spec dataset />
```

중간 조립 계층(catalog → compose → component)을 두지 않는다. `WidgetFrame` 은 `Card` 껍데기와 3상태 처리만 담당하고, 데이터 형태 변환은 각 렌더러 내부에서 끝난다.

### 3.2 타입 (`features/widgets/types.ts`)

```ts
export type WidgetTemplateId = string;

export type WidgetSpec = {
  template: WidgetTemplateId;
  title: string;
  query: {
    measure: string;
    dimensions: string[];
    filters: { field: string; op: string; value: string | number | string[] }[];
    projectScope: string[];
  };
  options: Record<string, unknown>;
};

export type WidgetColumn = {
  key: string;
  label: string;
  role: 'dimension' | 'measure' | 'label' | 'date' | 'status' | 'link';
  unit: string | null;
};

export type WidgetCell = string | number | boolean | null;

export type WidgetDataset = {
  columns: WidgetColumn[];
  rows: Record<string, WidgetCell>[];
  meta: {
    unit: string | null;
    total: number | null;
    previous: number | null;
    generatedAt: string;
    truncated: boolean;
  };
};

export type WidgetRenderProps = {
  spec: WidgetSpec;
  dataset: WidgetDataset;
};

export type WidgetRenderer = (props: WidgetRenderProps) => ReactNode;
```

**단일 데이터 봉투**를 쓴다. 템플릿마다 응답 스키마를 다르게 만들면 서버·클라이언트 양쪽에 8종 분기가 생긴다. `columns[].role` 로 렌더러가 필요한 열을 찾는다.

```ts
export const firstColumn = (dataset: WidgetDataset, role: WidgetColumn['role']) =>
  dataset.columns.find((column) => column.role === role) ?? null;
```

### 3.3 레지스트리 (`features/widgets/registry.ts`)

```ts
import type { WidgetRenderer } from '@/features/widgets/types';

export const widgetRenderers: Record<string, WidgetRenderer> = {
  'stat-card': StatCardWidget,
  'bar-chart': BarChartWidget,
  'line-chart': LineChartWidget,
  'pie-chart': PieChartWidget,
  'progress-list': ProgressListWidget,
  'data-table': DataTableWidget,
  'checklist': ChecklistWidget,
  'gantt-summary': GanttSummaryWidget,
};

export const resolveWidgetRenderer = (template: string): WidgetRenderer =>
  widgetRenderers[template] ?? UnsupportedWidget;
```

| 규칙 | 내용 |
| --- | --- |
| 타입 | 키는 `string`. `'stat-card' \| 'bar-chart' \| ...` 유니온을 선언하지 않는다(INV-28) |
| 추가 | 템플릿 추가 = 렌더러 파일 1개 + 이 맵에 1줄. 다른 파일을 고치지 않는다 |
| 폴백 | `UnsupportedWidget` — `Card` 안에 "지원하지 않는 템플릿: {template}" 1줄 + 위젯 삭제 버튼(편집 모드일 때). 예외를 던지지 않는다 |
| 격리 | `WidgetFrame` 이 `ErrorBoundary`(`components/common/WidgetErrorBoundary.tsx`)로 각 위젯을 감싼다. 위젯 1개의 렌더 에러가 대시보드 전체를 죽이지 않는다 |

### 3.4 템플릿 8종 입력 형태

`unit`·`sort`·`threshold` 등은 `spec.options` 에서 읽고, 없으면 기본값을 쓴다. 옵션 누락이 렌더 실패가 되면 안 된다.

| 템플릿 | 필요한 `columns.role` | 행 개수 | 사용 옵션 | shadcn 구성 |
| --- | --- | --- | --- | --- |
| `stat-card` | `measure` 1 | 1 | `unit`, `threshold{warn,critical}`, `precision` | `Card` + `Badge`(증감: `meta.previous` 대비) + `Separator`. 숫자는 `tabular-nums` |
| `bar-chart` | `dimension` 1 + `measure` 1..n | 1..50 | `unit`, `sort('asc'\|'desc')`, `stacked`, `layout('vertical')` | `Card` + `ChartContainer`/`ChartTooltip`/`ChartLegend` + recharts `BarChart` |
| `line-chart` | `date` 1 + `measure` 1..n | 1..365 | `unit`, `area(boolean)`, `showPlanned` | `Card` + `ChartContainer` + recharts `LineChart`/`AreaChart` |
| `pie-chart` | `dimension` 1 + `measure` 1 | 1..12 | `unit`, `innerRadius`, `showTotal` | `Card` + `ChartContainer` + recharts `PieChart`(도넛) |
| `progress-list` | `label` 1 + `measure` 1 | 1..20 | `unit`, `max`(기본 100), `sort` | `Card` + 행마다 `Progress` + 우측 수치 |
| `data-table` | 임의 조합(모든 열 표시) | 1..200 | `pageSize`(기본 10), `filterable`, `columns[]`(표시 순서) | `Card` + `Table` + `Pagination` + `Input`(필터) |
| `checklist` | `label` 1 + `status` 1 (+`date`) | 22 고정 | `showOnly('all'\|'missing')` | `Card` + `Table` + `Badge` |
| `gantt-summary` | `label` 1 + `date` 2(시작·종료) + `measure` 1(실적%) | 1..30 | `todayMarker`, `unit` | `Card` + `Table` + 커스텀 바(div + `bg-chart-*`). 라이브러리 없음 |

렌더러 예시 시그니처:

```tsx
export const StatCardWidget = ({ spec, dataset }: WidgetRenderProps) => { ... };
export const BarChartWidget = ({ spec, dataset }: WidgetRenderProps) => { ... };
```

**모든 렌더러는 `WidgetRenderProps` 하나만 받는다.** 렌더러가 데이터를 직접 가져오지 않는다(fetch 금지). 데이터 로딩은 `WidgetFrame` 의 `useWidgetData(widgetId)` 한 곳이다.

### 3.5 `WidgetFrame` 3상태

| 상태 | 렌더 |
| --- | --- |
| 로딩 | `Card` 유지 + 제목 표시 + 본문 `Skeleton`(템플릿별 높이 프리셋) |
| 빈값 | `dataset.rows.length === 0` → "해당 조건의 데이터 0건" 1줄 |
| 에러 | `Alert variant="destructive"` + `ErrorResponse.code` + [다시 시도] |
| 잘린 결과 | `meta.truncated` → 카드 하단 `Badge` "상위 200건" |

편집 모드에서는 카드 헤더 우측에 `DropdownMenu`(`ContextMenu` 대신 — 모바일·키보드 접근성) — [스펙 수정] [복제] [삭제]. 드래그 핸들은 카드 헤더 전체(`.widget-drag-handle`).

### 3.6 react-grid-layout 사용 방식

```tsx
<ResponsiveGridLayout
  className="layout"
  layouts={layouts}
  breakpoints={{ lg: 1200, md: 996, sm: 768 }}
  cols={{ lg: 12, md: 8, sm: 4 }}
  rowHeight={80}
  margin={[16, 16]}
  containerPadding={[0, 0]}
  draggableHandle=".widget-drag-handle"
  isDraggable={editing}
  isResizable={editing}
  onLayoutChange={(_current, all) => setDraftLayouts(all)}
  compactType="vertical"
/>
```

| 항목 | 확정값 |
| --- | --- |
| 브레이크포인트 | `lg 1200 / 12col`, `md 996 / 8col`, `sm 768 / 4col`. `xs`·`xxs` 를 쓰지 않는다 — 모바일 대시보드는 1열 세로 스택(`sm` 미만은 grid 를 끄고 `flex-col` 렌더) |
| rowHeight | 80px (PRD §4.3.1) |
| 기본 크기 | `stat-card` w3 h2 · 차트 3종 w6 h4 · `progress-list` w4 h4 · `data-table` w8 h5 · `checklist` w6 h6 · `gantt-summary` w12 h5 |
| 편집 모드 진입 | 툴바 `Switch` "편집". CLIENT 만 렌더 |
| 편집 중 상태 | `draftLayouts` 는 컴포넌트 `useState` 에만 존재. **저장 전에는 서버에도 클라이언트 저장소에도 쓰지 않는다** |
| 저장 타이밍 | **명시적 [저장] 버튼 1회** → `PUT /api/dashboards/{id}/layout {layouts}`. 자동 저장·디바운스 저장 없음 |
| 취소 | `draftLayouts` 버리고 `invalidate('/api/dashboards/{id}')` 로 서버 상태 재조회(ADR-007) |
| 이탈 방지 | 편집 중 라우트 이탈 시 `useBlocker` + `AlertDialog` "저장하지 않은 변경이 있습니다" |
| localStorage | 사용 금지. `react-grid-layout` 자체 저장 기능도 쓰지 않는다 |
| 위젯 추가 | 저장 후 서버가 새 위젯의 초기 좌표를 계산해 `layout_json` 에 반영, 프론트는 재조회 |

### 3.7 위젯 생성 마법사 (3단계 Dialog)

```
Step 1 템플릿 선택          Step 2 내용 정의            Step 3 미리보기
┌──────────────────┐       ┌────────────────────┐     ┌──────────────────┐
│ RadioGroup 카드8 │  →    │ Tabs[프롬프트|지표]│  →  │ WidgetFrame 실물 │
│ [stat][bar][line]│       │ Textarea 프롬프트  │     │ 제목 Input 수정  │
│ [pie][prog][tbl] │       │ 또는 Select measure│     │ [뒤로][대시보드 │
│ [check][gantt]   │       │ 프로젝트 범위 선택 │     │       에 추가]   │
└──────────────────┘       └────────────────────┘     └──────────────────┘
```

| 항목 | 내용 |
| --- | --- |
| shadcn/ui | `Dialog`, `RadioGroup`(템플릿 카드), `Tabs`, `Textarea`, `Select`, `Command`(프로젝트 범위 다중 선택), `Button`, `Alert`, `Skeleton` |
| 템플릿 카탈로그 | 하드코딩하지 않는다. `GET /api/semantic/widget-templates` → `[{id,label,description,previewShape}]`. 프론트는 `resolveWidgetRenderer` 로 지원 여부만 표시 |
| 스펙 생성 | `POST /api/widgets/spec {template, prompt, projectScope}` → 서버가 `glm-5.2:cloud` tool calling + 카탈로그 재검증 후 `WidgetSpec` 반환 |
| 실패 처리 | `CATALOG_VALIDATION_FAILED` → `Alert` + [Q&A로 질문하기] 버튼(`/ask` 로 프롬프트 전달, ADR-004) |
| 미리보기 | `POST /api/widgets/preview {spec}` → `WidgetDataset`. 저장 전 실물 렌더러로 그린다 |
| 확정 | `POST /api/dashboards/{id}/widgets {spec}` → 서버가 위젯 + 레이아웃 좌표 반환 → 재조회 |

---

## 4. AI Q&A 화면 설계

### 4.1 레이아웃 (Gemini 준용)

```
┌ AppShell ───────────────────────────────────────────────────────────┐
│┌ 대화 사이드바 280px ─┐┌ 스레드 (최대 폭 768px 중앙) ───────────────┐│
││ [+ 새 대화]          ││ ┌ 사용자 메시지 (우측 정렬 bubble) ───────┐││
││ ─── 고정 ───         ││ │ 이번 주 지연된 산출물은?               │││
││ 📌 검수 준비 [PROJ-A]││ └────────────────────────────────────────┘││
││ ─── 최근 ───         ││ 어시스턴트 메시지                          ││
││ 산출물 현황  [전체]  ││ 산출물 3건이 지연 상태입니다[1]. 시험결과 ││
││ 이슈 처리율  [PROJ-B]││ 서는 승인 대기입니다[2].                   ││
││   ⋮ DropdownMenu     ││ ┌ Collapsible 출처 (2) ──────────────────┐││
││     핀 / 이름변경 /  ││ │ [1] 요구사항정의서 v1.2 · p.14  ↗      │││
││     삭제             ││ │ [2] PROJ-231 시험결과서 · Jira  ↗      │││
││                      ││ └────────────────────────────────────────┘││
││                      ││ [👍][👎][복사]                             ││
││                      ││                                            ││
││                      ││ ┌ Composer ─────────────────────────────┐ ││
││                      ││ │ [범위: PROJ-A ▾] Textarea…    [전송]  │ ││
││                      ││ └───────────────────────────────────────┘ ││
│└──────────────────────┘└────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘

초기 화면(메시지 0건): 중앙 정렬 Composer + 추천 질문 칩 4개
```

| 영역 | shadcn/ui |
| --- | --- |
| 대화 사이드바 | `Sidebar`(중첩 — `SidebarProvider` 는 앱셸 것을 재사용하지 않고 별도 `aside` + `ScrollArea`), `Button`, `DropdownMenu`, `Badge`(프로젝트 태그), `Input`(대화 검색) |
| 스레드 | `ScrollArea`, `Skeleton`(첫 토큰 전), `Separator` |
| 어시스턴트 답변 | 커스텀 `AnswerBody`(각주 파싱) + `Button variant="link"`(각주) |
| 출처 | `Collapsible` + `Card`(출처 카드) + `Badge`(도구 아이콘 자리) + 외부 링크 `Button variant="ghost"` |
| 각주 미리보기 | `HoverCard`(스니펫 3줄 + 출처명) |
| 입력 | `Textarea`(자동 높이), `Button`(전송/중지), `Select` 또는 `Command`(프로젝트 범위), `Badge`(선택된 범위) |
| 평가 | `Button variant="ghost" size="icon"` 👍/👎, `Tooltip` |
| 추천 칩 | `Button variant="outline" size="sm"` 4개 |

`/p/:projectId/ask` 로 진입하면 범위 선택기는 해당 프로젝트로 고정되고 `disabled` 다.

### 4.2 SSE 소비 방식

`EventSource` 를 쓰지 않는다 — POST 본문과 `Authorization` 헤더가 필요하기 때문이다. `fetch` + `ReadableStream` 으로 직접 파싱한다(`api/sse.ts`).

```ts
export type SseFrame = { event: string; data: string };

export async function* readSse(response: Response, signal: AbortSignal): AsyncGenerator<SseFrame> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      yield parseFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
    }
  }
  await reader.cancel();
}
```

서버 프레임 규격(`01-conceptual-architecture.md` §4.2 와 1:1):

| 프레임 | 페이로드 | 프론트 처리 |
| --- | --- | --- |
| `data: {"delta":"..."}` | 토큰 조각 | `streamingText += delta` (React 19 자동 배칭에 맡기고 별도 스로틀 없음) |
| `data: {"sources":[...]}` | `MessageSource[]` | `sources` 상태 세팅. 각주 렌더 활성화 |
| `event: done` `data: {"messageId","conversationId","seq"}` | 종료 | 스트리밍 버퍼를 확정 메시지로 커밋, 대화 목록 `invalidate` |
| `event: error` `data: {"code","message"}` | 실패 | 스트리밍 버퍼 폐기 + `Alert` 로 코드·메시지 표시 |

### 4.3 상태 관리 (`useAskStream`)

```ts
type AskStreamState = {
  status: 'idle' | 'streaming' | 'done' | 'aborted' | 'error';
  text: string;
  sources: MessageSource[];
  error: ApiError | null;
};

export const useAskStream = (conversationId: string | null) => {
  const controller = useRef<AbortController | null>(null);
  const ask = async (question: string, projectScope: string[]) => { ... };
  const stop = () => controller.current?.abort();
  return { state, ask, stop };
};
```

| 규칙 | 내용 |
| --- | --- |
| 상태 위치 | 스트리밍 상태는 `AskPage` 지역 상태. 전역 스토어를 두지 않는다 |
| 확정 메시지 | `event: done` 이후 `GET /api/conversations/{cid}/messages` 재조회로 대체하지 않고, `done` 페이로드로 즉시 커밋 → 재조회는 사이드바 목록만 |
| 중지 | `AbortController.abort()` → 서버가 스트림을 닫고 `message` 를 저장하지 않는다. 프론트도 버퍼를 버린다 |
| 전송 중 입력 | 전송 버튼이 [중지]로 바뀐다. `Textarea` 는 계속 입력 가능하되 Enter 전송은 막는다 |
| 접근성 | 스트리밍 영역 `aria-live="polite"` `aria-busy` |
| 스크롤 | 사용자가 위로 스크롤하면 자동 하단 고정 해제, [최신으로] 버튼 표시 |

### 4.4 각주 `[n]` ↔ 출처 카드 연동

```tsx
const FOOTNOTE = /\[(\d+)\]/g;

export const AnswerBody = ({ text, sources, activeFootnote, onFootnote }: AnswerBodyProps) =>
  splitByFootnote(text).map((part) =>
    part.footnoteNo === null ? (
      <span key={part.key}>{part.text}</span>
    ) : (
      <HoverCard key={part.key}>
        <HoverCardTrigger asChild>
          <button
            type="button"
            data-active={activeFootnote === part.footnoteNo}
            onClick={() => onFootnote(part.footnoteNo)}
            className="mx-0.5 rounded bg-muted px-1 text-xs tabular-nums data-[active=true]:bg-primary data-[active=true]:text-primary-foreground"
          >
            {part.footnoteNo}
          </button>
        </HoverCardTrigger>
        <HoverCardContent>{sourceOf(sources, part.footnoteNo)?.snippet}</HoverCardContent>
      </HoverCard>
    ),
  );
```

| 동작 | 구현 |
| --- | --- |
| 각주 클릭 | `setActiveFootnote(n)` → 출처 카드로 `scrollIntoView({block:'nearest'})` + 카드에 `ring-2 ring-primary` 1.5초 |
| 출처 카드 hover | 같은 번호의 본문 각주에 `data-active` 부여(역방향 하이라이트) |
| 대응 없는 각주 | 서버가 이미 제거한다(INV-31). 프론트는 `sources` 에 없는 번호를 만나면 일반 텍스트로 렌더 |
| 딥링크 | `source.externalUrl` 이 있으면 `target="_blank" rel="noreferrer"`, 업로드 문서면 `/p/{pid}/documents/{did}?page={n}` 내부 뷰어 |
| 마크다운 | 렌더링하지 않는다. 줄바꿈·목록만 `whitespace-pre-wrap` 으로 처리한다(라이브러리 추가 금지) |

### 4.5 대화 관리 · 추천 칩

| 기능 | API | UI |
| --- | --- | --- |
| 목록 | `GET /api/conversations` | 사이드바(고정/최근 2섹션) |
| 생성 | `POST /api/conversations {projectScope}` | [+ 새 대화] — 첫 질문 전송 시 서버가 제목 자동 생성 |
| 핀 | `PATCH /api/conversations/{cid} {pinned}` | DropdownMenu |
| 삭제 | `DELETE /api/conversations/{cid}` | `AlertDialog` 확인 |
| 메시지 | `GET /api/conversations/{cid}/messages` | 진입 시 1회 |
| 평가 | `POST /api/messages/{mid}/feedback {value}` | 👍/👎 토글 |
| 추천 칩 | `GET /api/qna/suggestions?projectScope=` | 초기 화면에만 4개. 실패하면 칩 영역을 렌더하지 않는다(에러 표시 없음) |

---

## 5. 디렉터리 구조와 파일 목록

```
frontend/
  index.html
  vite.config.ts
  tsconfig.json
  components.json            shadcn CLI 설정 (style=new-york, baseColor=zinc, css variables)
  src/
```

### 5.1 루트·공통

| 파일 | 책임 |
| --- | --- |
| `src/main.tsx` | React 루트 마운트, `RouterProvider` 연결 |
| `src/App.tsx` | 라우터 정의(`createBrowserRouter`)와 전역 `Toaster`·`ThemeProvider` 조립 |
| `src/routes.tsx` | 라우트 트리 단일 정의(§1.2 표 그대로) |
| `src/index.css` | Tailwind v4 진입점 + 디자인 토큰(§7) |
| `src/vite-env.d.ts` | Vite 환경 타입 |

### 5.2 `components/`

| 파일 | 책임 |
| --- | --- |
| `components/ui/*.tsx` | shadcn CLI 생성물(§5.7 설치 목록). 직접 수정은 토큰 참조만 |
| `components/ui/dropzone.tsx` | 파일 드롭존 — 네이티브 `input[type=file]` + drag 이벤트, shadcn 스타일 규격 커스텀 |
| `components/layout/AuthLayout.tsx` | 로그인·초대 전용 중앙 정렬 셸 |
| `components/layout/AppShell.tsx` | 사이드바+헤더+아웃렛+Toaster 앱셸 |
| `components/layout/AppSidebar.tsx` | 전역 내비게이션 메뉴(역할별 항목 필터) |
| `components/layout/AppHeader.tsx` | 사이드바 토글·Breadcrumb·테마 토글·UserMenu |
| `components/layout/Breadcrumbs.tsx` | 라우트 매치로 경로 조각 생성 |
| `components/layout/UserMenu.tsx` | 계정 드롭다운(이름·조직·역할·로그아웃) |
| `components/layout/ProjectLayout.tsx` | 프로젝트 헤더·탭·접근 판정 후 아웃렛 |
| `components/layout/ProjectNav.tsx` | 프로젝트 내부 탭 목록(권한별 항목 필터) |
| `components/layout/RequireAuth.tsx` | 세션 부트스트랩 대기 + 미인증 리다이렉트 |
| `components/layout/RequireRole.tsx` | 역할 게이트 |
| `components/layout/ThemeProvider.tsx` | 라이트/다크/시스템 테마 클래스 토글 |
| `components/common/DataState.tsx` | 로딩·빈값·에러 3상태 단일 분기 컴포넌트 |
| `components/common/EmptyState.tsx` | 빈값 표시(문구 + 선택적 액션) |
| `components/common/ErrorAlert.tsx` | `ApiError` 를 `Alert` 로 렌더 + 재시도 |
| `components/common/PageHeader.tsx` | 화면 제목 + 우측 액션 슬롯 |
| `components/common/StatusBadge.tsx` | 상태 문자열 → Badge variant·라벨 매핑(표준 상태 전용) |
| `components/common/DateRange.tsx` | 착수일·마감일 한 쌍 표기(열린 기간 금지) |
| `components/common/ConfirmDialog.tsx` | 파괴적 액션 공통 `AlertDialog` 래퍼 |
| `components/common/WidgetErrorBoundary.tsx` | 위젯 단위 렌더 에러 격리 |
| `components/common/ForbiddenPage.tsx` | 403 화면 |
| `components/common/NotFoundPage.tsx` | 404 화면 |

### 5.3 `api/` · `lib/` · `types/` · `standard/`

| 파일 | 책임 |
| --- | --- |
| `api/client.ts` | `apiFetch` — 베이스 URL·헤더·JSON 직렬화·에러 변환·401 재발급 |
| `api/errors.ts` | `ApiError` 클래스와 `ErrorCode` 상수 |
| `api/query.ts` | `useApiQuery` / `useApiMutation` / `invalidate` — 모듈 캐시 기반 서버 상태 훅 |
| `api/sse.ts` | SSE 프레임 파서(`readSse`)와 `postSse` 헬퍼 |
| `api/session.ts` | 액세스 토큰 메모리 보관·재발급 단일 비행·로그아웃 |
| `lib/utils.ts` | `cn`(clsx + tailwind-merge) |
| `lib/format.ts` | 숫자·퍼센트·바이트·소요시간 포맷 |
| `lib/date.ts` | 날짜 포맷·기간 표기·상대시간(`Intl` 사용, 라이브러리 없음) |
| `types/auth.ts` | `Session`, `Role`, `Invitation` |
| `types/project.ts` | `Project`, `ProjectSummary`, `ProjectPermissions`, `ClosureGate` |
| `types/assignment.ts` | `Assignment`, `AssignmentPermissions` |
| `types/connection.ts` | `ToolConnection`, `MappingRule`, `ConnectionTestResult` |
| `types/sync.ts` | `SyncJob`, `SyncJobStatus` |
| `types/document.ts` | `DocumentUpload`, `StructuringDraft`, `ExtractedRequirement` |
| `types/standard.ts` | `WorkProduct`, `Requirement`, `TraceRow`, `ChangeRequest`, `CorrectionAction`, `AcceptanceRecord` |
| `types/dashboard.ts` | `Dashboard`, `Widget`, `LayoutMap` |
| `types/qna.ts` | `Conversation`, `Message`, `MessageSource`, `AskFrame` |
| `standard/workProductTypes.ts` | 22종 enum 값·화면 이름·주 활동 단일 정의(INV-18) |
| `standard/iso29110Activities.ts` | `PM.1~PM.4`, `SI.1~SI.6` 단일 정의 |
| `standard/statusLabels.ts` | 표준 엔티티 상태값 → 한글 라벨·Badge variant 매핑 |

`standard/*` 는 **enum·라벨 정의**이지 데이터가 아니다. 목업 데이터 금지 규칙에 저촉되지 않는다.

### 5.4 `features/` — 도메인별

| 파일 | 책임 |
| --- | --- |
| **auth** | |
| `features/auth/LoginPage.tsx` | 로그인 폼과 역할별 초기 경로 이동 |
| `features/auth/AcceptInvitePage.tsx` | 초대 토큰 검증 + 비밀번호 설정 |
| `features/auth/api.ts` | 로그인·로그아웃·초대·세션 조회 호출 |
| `features/auth/useSession.ts` | 현재 세션 컨텍스트 훅(역할·조직·권한) |
| **projects** | |
| `features/projects/ProjectListPage.tsx` | 프로젝트 카드 목록·검색·필터·생성 Dialog 마운트 |
| `features/projects/ProjectCard.tsx` | 카드 1개(상태·기간·승인률·열린 조치) |
| `features/projects/ProjectCreateDialog.tsx` | 생성 폼(필수 4필드 + 기간 검증) |
| `features/projects/ProjectOverviewPage.tsx` | 개요 KPI·최근 동기화·열린 시정조치 |
| `features/projects/api.ts` | 프로젝트 목록·상세·요약·생성·종료 호출 |
| `features/projects/hooks.ts` | `useProject`, `useProjectSummary`, `useProjectPermissions` |
| **assignments** | |
| `features/assignments/AssignmentsPage.tsx` | 할당 목록 테이블과 해제 |
| `features/assignments/AssignContractorSheet.tsx` | 조직·계정 선택 + 권한 토글 후 할당 |
| `features/assignments/PermissionSwitches.tsx` | 권한 3종 스위치(낙관적 갱신) |
| `features/assignments/api.ts` | 할당 조회·생성·권한 변경·해제 호출 |
| **connections** | |
| `features/connections/ConnectionsPage.tsx` | 연결 카드 목록·추가·삭제 |
| `features/connections/ConnectionFormDialog.tsx` | 도구별 입력 폼 + 연결 테스트 게이트 |
| `features/connections/ConnectionCard.tsx` | 연결 1개 상태·최근 동기화·액션 |
| `features/connections/MappingRulesPage.tsx` | 매핑 규칙 편집 테이블과 재적용 선택 |
| `features/connections/api.ts` | 연결 CRUD·테스트·매핑 규칙·백필 호출 |
| **collection** | |
| `features/collection/SyncStatusPage.tsx` | 동기화 잡 목록·필터·재시도·조건부 폴링 |
| `features/collection/SyncJobRow.tsx` | 잡 1행(상태 Badge·오류 Tooltip·재시도) |
| `features/collection/api.ts` | 잡 목록·재시도 호출 |
| **documents** | |
| `features/documents/DocumentsPage.tsx` | 업로드 드롭존 + 문서 목록 + 상태 폴링 |
| `features/documents/UploadDropzone.tsx` | 파일 선택·검증·진행률 표시 |
| `features/documents/StructuringConfirmDialog.tsx` | 정형화 초안 확정(유형·제목·버전·요구사항) |
| `features/documents/ExtractedRequirementTable.tsx` | 추출 요구사항 선택·우선순위 편집 |
| `features/documents/api.ts` | 업로드·목록·초안·확정·반려 호출 |
| **deliverables** | |
| `features/deliverables/DeliverableChecklistPage.tsx` | 22종 점검표 테이블과 승인률 |
| `features/deliverables/DeliverableRow.tsx` | 산출물 1행(상태·버전·활동) |
| `features/deliverables/DeliverableDetailSheet.tsx` | 버전 이력·파일 링크·승인 액션 |
| `features/deliverables/api.ts` | 산출물 조회·승인·반려·제출 호출 |
| **traceability** | |
| `features/traceability/TraceabilityPage.tsx` | 추적표 테이블·필터·추적률 |
| `features/traceability/TraceCell.tsx` | 링크 유무 셀(HoverCard 링크 목록·끊김 Badge) |
| `features/traceability/api.ts` | 추적표 조회 호출 |
| **changes** | |
| `features/changes/ChangesPage.tsx` | 변경요청·시정조치 2탭 |
| `features/changes/ChangeRequestTable.tsx` | 변경요청 목록·상태 전이 |
| `features/changes/CorrectionActionTable.tsx` | 시정조치 목록·기한 강조·완료 처리 |
| `features/changes/api.ts` | 변경·시정 CRUD 호출 |
| **closure** | |
| `features/closure/ClosurePage.tsx` | 종료 게이트 + 검수확인서 카드 |
| `features/closure/AcceptanceRecordForm.tsx` | 검수확인서 등록 폼 |
| `features/closure/CloseProjectDialog.tsx` | 종료 확정 AlertDialog |
| `features/closure/api.ts` | 검수확인서·게이트·종료 호출 |
| **dashboard** | |
| `features/dashboard/DashboardPage.tsx` | 대시보드 선택·툴바·그리드 조립 |
| `features/dashboard/DashboardToolbar.tsx` | 대시보드 Select·편집 Switch·저장/취소·위젯 추가 |
| `features/dashboard/DashboardGrid.tsx` | react-grid-layout 배치와 draft 레이아웃 상태 |
| `features/dashboard/WidgetFrame.tsx` | 위젯 Card 껍데기·데이터 로딩·3상태·편집 메뉴 |
| `features/dashboard/WidgetCreateDialog.tsx` | 3단계 위젯 생성 마법사 |
| `features/dashboard/TemplatePicker.tsx` | 템플릿 카탈로그 RadioGroup 카드 |
| `features/dashboard/WidgetContentStep.tsx` | 프롬프트/지표 선택 + 프로젝트 범위 |
| `features/dashboard/WidgetPreviewStep.tsx` | 미리보기 렌더 + 제목 확정 |
| `features/dashboard/useDashboard.ts` | 대시보드·위젯 조회와 레이아웃 저장 |
| `features/dashboard/useWidgetData.ts` | 위젯 데이터 조회·수동 새로고침 |
| `features/dashboard/api.ts` | 대시보드·위젯·스펙 생성·미리보기 호출 |
| **widgets** | |
| `features/widgets/types.ts` | `WidgetSpec`·`WidgetDataset`·`WidgetRenderer` 타입 |
| `features/widgets/registry.ts` | 템플릿 → 렌더러 레코드 맵과 폴백 해석 |
| `features/widgets/dataset.ts` | `columns.role` 기반 열 조회 헬퍼 |
| `features/widgets/chartConfig.ts` | recharts용 `ChartConfig` 생성(색상 토큰 배정) |
| `features/widgets/renderers/StatCardWidget.tsx` | 단일 KPI + 증감 배지 |
| `features/widgets/renderers/BarChartWidget.tsx` | 차원 1개 비교 막대 |
| `features/widgets/renderers/LineChartWidget.tsx` | 기간 추이 라인/영역 |
| `features/widgets/renderers/PieChartWidget.tsx` | 구성비 도넛 |
| `features/widgets/renderers/ProgressListWidget.tsx` | 항목별 진행률 목록 |
| `features/widgets/renderers/DataTableWidget.tsx` | 정렬·페이징 테이블 |
| `features/widgets/renderers/ChecklistWidget.tsx` | 22종 점검표 축약 |
| `features/widgets/renderers/GanttSummaryWidget.tsx` | 계획 대비 실적 바 요약 |
| `features/widgets/renderers/UnsupportedWidget.tsx` | 미지원 템플릿 폴백 카드 |
| **ask** | |
| `features/ask/AskPage.tsx` | Q&A 화면 조립·스트리밍 상태 소유 |
| `features/ask/ConversationSidebar.tsx` | 대화 목록·검색·핀·삭제 |
| `features/ask/MessageThread.tsx` | 메시지 목록·자동 스크롤 |
| `features/ask/UserMessage.tsx` | 사용자 턴 렌더 |
| `features/ask/AssistantMessage.tsx` | 답변 본문 + 출처 + 평가 조립 |
| `features/ask/AnswerBody.tsx` | 각주 `[n]` 파싱·하이라이트·HoverCard |
| `features/ask/SourceList.tsx` | 출처 카드 목록(Collapsible) |
| `features/ask/SourceCard.tsx` | 출처 1건(제목·도구·딥링크·스니펫) |
| `features/ask/Composer.tsx` | 입력·전송/중지·범위 선택 |
| `features/ask/ScopeSelector.tsx` | 프로젝트 범위 다중 선택(권한 내) |
| `features/ask/SuggestionChips.tsx` | 추천 질문 칩 4개 |
| `features/ask/useAskStream.ts` | SSE 소비·중지·프레임 상태 관리 |
| `features/ask/api.ts` | 대화·메시지·평가·추천 호출 |
| **admin** | |
| `features/admin/OrganizationsPage.tsx` | 조직 목록·등록·수정 |
| `features/admin/OrganizationFormDialog.tsx` | 조직 입력 폼 |
| `features/admin/UsersPage.tsx` | 계정 목록·생성·초대 재발송·비활성화 |
| `features/admin/UserFormDialog.tsx` | 계정 입력 폼(조직·역할) |
| `features/admin/AuditLogPage.tsx` | 감사 로그 조회·필터·페이징 |
| `features/admin/api.ts` | 조직·계정·감사 호출 |

### 5.5 테스트 파일 (최소 세트)

| 파일 | 검증 대상 |
| --- | --- |
| `src/standard/workProductTypes.test.ts` | 22종 값·개수가 서버 enum 스냅샷(`GET /api/standard/enums` 픽스처)과 1:1 일치(INV-18) |
| `src/features/widgets/registry.test.tsx` | 8종 매핑 존재 + 미지원 템플릿이 `UnsupportedWidget` 으로 폴백하고 예외를 던지지 않음(INV-28) |
| `src/features/ask/AnswerBody.test.tsx` | 각주 파싱: 대응 있는 `[n]` 은 버튼, 없는 `[n]` 은 평문(INV-31) |
| `src/api/query.test.ts` | 동일 키 동시 호출이 요청 1회로 합쳐지고 `invalidate` 후 재요청됨 |

프레임워크는 Vitest 하나. 화면별 렌더 테스트 스위트는 만들지 않는다.

### 5.6 금지 파일

`src/**/mocks/*`, `src/**/fixtures/*`(테스트 픽스처 제외), `src/**/*.mock.ts`, 화면 데이터가 담긴 상수 배열 파일. 생성 시 리뷰에서 반려한다.

### 5.7 shadcn/ui 설치 목록

```
alert  alert-dialog  avatar  badge  breadcrumb  button  calendar  card  chart
checkbox  collapsible  command  dialog  dropdown-menu  form  hover-card  input
label  pagination  popover  progress  radio-group  scroll-area  select  separator
sheet  sidebar  skeleton  sonner  switch  table  tabs  textarea  tooltip
```

추가 커스텀: `components/ui/dropzone.tsx` 1개. 그 외 커스텀 UI 를 만들 때는 위 목록 재조합을 먼저 시도하고, 불가할 때만 radix 프리미티브(`@radix-ui/react-*`)를 직접 조합해 같은 디렉터리에 둔다.

---

## 6. API 클라이언트 계층

### 6.1 `api/client.ts`

```ts
const BASE = '/api';

export const apiFetch = async <T>(path: string, init: ApiInit = {}): Promise<T> => {
  const response = await withAuth(path, init);
  if (response.status === 204) return undefined as T;
  const payload = await readJson(response);
  if (!response.ok) throw ApiError.from(response.status, payload);
  return payload as T;
};

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PATCH', body }),
  del: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData, onProgress?: (ratio: number) => void) => ...,
};
```

| 항목 | 규칙 |
| --- | --- |
| 타입 안전 | 제네릭 `T` 는 호출부에서 `types/*` 의 타입을 명시한다. `any` 금지, 응답 검증은 서버 계약을 신뢰하고 런타임 파서를 두지 않는다 |
| 직렬화 | `body` 가 `FormData` 면 그대로, 아니면 `JSON.stringify` + `Content-Type: application/json` |
| 업로드 진행률 | `fetch` 는 업로드 진행률을 주지 않으므로 `api.upload` 만 `XMLHttpRequest` 를 쓴다(진행률 표시가 요구사항이므로 예외) |
| 쿼리스트링 | `URLSearchParams`. 직접 문자열 연결 금지 |

### 6.2 에러 처리 (`api/errors.ts`)

```ts
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown>,
  ) { super(message); }
}
```

| 상태 | 처리 |
| --- | --- |
| 400 / 422 | 폼 필드 오류로 매핑(`details.fieldErrors` → react-hook-form `setError`) |
| 401 | `api/session.ts` 가 재발급 1회 시도 → 실패 시 세션 소거 + `/login?next=` |
| 403 `PROJECT_ACCESS_DENIED` | 라우트를 `/403` 으로 교체 |
| 404 | 화면 내 `EmptyState` 또는 `/404` |
| 409 / 412 | `Sonner` 토스트 + 해당 쿼리 `invalidate` |
| 503 `AI_UNAVAILABLE` | 화면에 원인 그대로 표시. 재시도 버튼만 제공하고 대체 답변을 만들지 않는다 |
| 그 외 5xx | `ErrorAlert` + 재시도 |

전역 토스트로 삼키지 않는다. 에러는 요청을 유발한 화면 영역에 표시한다.

### 6.3 인증 토큰 (`api/session.ts`)

| 항목 | 방식 |
| --- | --- |
| 액세스 토큰 | **메모리 모듈 변수**. `localStorage`·`sessionStorage`·쿠키에 저장하지 않는다 |
| 리프레시 토큰 | 서버가 `HttpOnly; Secure; SameSite=Lax` 쿠키로 발급·회전. 프론트 코드가 접근하지 않는다 |
| 부트스트랩 | 앱 기동 시 `POST /api/auth/refresh` 1회 → 성공하면 세션 복원, 실패하면 미인증 |
| 재발급 | 401 응답 시 단일 비행(`refreshPromise` 공유)으로 `POST /api/auth/refresh` → 성공 시 원 요청 **1회만** 재시도 |
| 로그아웃 | `POST /api/auth/logout` + 메모리 토큰 제거 + 캐시 전체 폐기 |
| 헤더 | `Authorization: Bearer {accessToken}`. 토큰을 URL 쿼리로 보내지 않는다 |

### 6.4 서버 상태 캐싱 (`api/query.ts`)

라이브러리를 추가하지 않는다. 필요한 기능은 4개뿐이다: 캐시, 중복 요청 합치기, 무효화, 조건부 폴링.

```ts
type Entry<T> = { data: T | null; error: ApiError | null; at: number; inflight: Promise<T> | null };

const cache = new Map<string, Entry<unknown>>();
const listeners = new Map<string, Set<() => void>>();

export const useApiQuery = <T>(key: string | null, options: QueryOptions = {}) => {
  // key === null → 비활성(조건부 조회)
  // 마운트 시 staleTime(기본 30초) 지난 항목만 재요청
  // 같은 key 동시 요청은 inflight 프라미스를 공유
  // options.refetchInterval 이 있으면 setInterval 로 재요청
  return { data, error, loading, refetch } as QueryResult<T>;
};

export const useApiMutation = <TBody, TResult>(
  run: (body: TBody) => Promise<TResult>,
  options: { invalidates?: string[] } = {},
) => ({ mutate, pending, error });

export const invalidate = (prefix: string) => { /* prefix 로 시작하는 key 전부 stale 처리 + 구독자 알림 */ };
```

| 규칙 | 내용 |
| --- | --- |
| 캐시 키 | 요청 경로 문자열 그대로(`/api/projects?scope=mine`). 별도 키 튜플 규약을 만들지 않는다 |
| staleTime | 기본 30초. 대시보드 위젯 데이터 60초, 동기화 잡 0초 |
| 무효화 | 변이 성공 시 `invalidates: ['/api/projects']` 처럼 **경로 프리픽스** 지정 |
| 낙관적 갱신 | 권한 토글 1곳만 사용. 그 외에는 재조회로 처리한다 |
| 폴링 | `refetchInterval` 은 화면이 요구할 때만(동기화 현황, 문서 정형화 진행). 언마운트 시 해제 |
| 저장소 | 캐시는 메모리 전용. 디스크 영속화 없음 |

### 6.5 SSE (`api/sse.ts`)

```ts
export const postSse = async (
  path: string,
  body: unknown,
  signal: AbortSignal,
): Promise<AsyncGenerator<SseFrame>> => { ... };
```

| 규칙 | 내용 |
| --- | --- |
| 방식 | `fetch(..., { method: 'POST', headers: { Accept: 'text/event-stream', Authorization } , signal })` |
| 파싱 | `\n\n` 경계 분할 → `event:`/`data:` 라인 파싱. 여러 `data:` 라인은 `\n` 으로 결합 |
| 401 | 스트림 시작 전 상태코드로 판정 → 재발급 후 1회 재시도 |
| 중지 | `AbortController.abort()` 로 즉시 종료, `reader.cancel()` 호출 |
| 캐시 | SSE 응답은 `useApiQuery` 캐시에 넣지 않는다 |

---

## 7. 디자인 토큰

### 7.1 원칙

| 원칙 | 내용 |
| --- | --- |
| 기반 | shadcn/ui 기본 토큰 세트(`--background`, `--foreground`, `--card`, `--popover`, `--primary`, `--secondary`, `--muted`, `--accent`, `--destructive`, `--border`, `--input`, `--ring`, `--chart-1..5`, `--sidebar-*`)를 그대로 유지한다 |
| 확장 | `--success`, `--warning` 2쌍(+`-foreground`)만 추가한다. 상태 Badge 5종(none/draft/submitted/approved/rejected)을 표현하려면 destructive 만으로 부족하다 |
| 색공간 | oklch. `components.json` 의 `cssVariables: true` |
| 하드코딩 | 컴포넌트에 `#hex`·`rgb()`·Tailwind 색 유틸(`bg-blue-500`) 사용 금지. 토큰 유틸(`bg-primary`, `text-muted-foreground`)만 |
| 다크 | `.dark` 클래스 토글(`ThemeProvider`). `prefers-color-scheme` 은 초기값 결정에만 사용 |

### 7.2 `src/index.css`

```css
@import 'tailwindcss';
@import 'tw-animate-css';

@custom-variant dark (&:is(.dark *));

:root {
  --radius: 0.625rem;

  --background: oklch(1 0 0);
  --foreground: oklch(0.21 0.01 258);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.21 0.01 258);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.21 0.01 258);

  --primary: oklch(0.51 0.15 258);
  --primary-foreground: oklch(0.98 0.005 258);
  --secondary: oklch(0.96 0.006 258);
  --secondary-foreground: oklch(0.28 0.02 258);
  --muted: oklch(0.96 0.006 258);
  --muted-foreground: oklch(0.53 0.02 258);
  --accent: oklch(0.95 0.02 258);
  --accent-foreground: oklch(0.28 0.02 258);

  --destructive: oklch(0.58 0.21 27);
  --destructive-foreground: oklch(0.98 0.005 258);
  --success: oklch(0.62 0.14 156);
  --success-foreground: oklch(0.98 0.005 258);
  --warning: oklch(0.75 0.15 78);
  --warning-foreground: oklch(0.24 0.03 78);

  --border: oklch(0.91 0.008 258);
  --input: oklch(0.91 0.008 258);
  --ring: oklch(0.51 0.15 258);

  --chart-1: oklch(0.51 0.15 258);
  --chart-2: oklch(0.63 0.13 196);
  --chart-3: oklch(0.62 0.14 156);
  --chart-4: oklch(0.75 0.15 78);
  --chart-5: oklch(0.58 0.18 320);

  --sidebar: oklch(0.985 0.003 258);
  --sidebar-foreground: oklch(0.21 0.01 258);
  --sidebar-primary: oklch(0.51 0.15 258);
  --sidebar-primary-foreground: oklch(0.98 0.005 258);
  --sidebar-accent: oklch(0.95 0.02 258);
  --sidebar-accent-foreground: oklch(0.28 0.02 258);
  --sidebar-border: oklch(0.91 0.008 258);
  --sidebar-ring: oklch(0.51 0.15 258);
}

.dark {
  --background: oklch(0.18 0.012 258);
  --foreground: oklch(0.96 0.005 258);
  --card: oklch(0.22 0.014 258);
  --card-foreground: oklch(0.96 0.005 258);
  --popover: oklch(0.22 0.014 258);
  --popover-foreground: oklch(0.96 0.005 258);

  --primary: oklch(0.68 0.13 258);
  --primary-foreground: oklch(0.18 0.012 258);
  --secondary: oklch(0.27 0.016 258);
  --secondary-foreground: oklch(0.96 0.005 258);
  --muted: oklch(0.27 0.016 258);
  --muted-foreground: oklch(0.70 0.015 258);
  --accent: oklch(0.30 0.03 258);
  --accent-foreground: oklch(0.96 0.005 258);

  --destructive: oklch(0.65 0.19 27);
  --destructive-foreground: oklch(0.18 0.012 258);
  --success: oklch(0.70 0.13 156);
  --success-foreground: oklch(0.18 0.012 258);
  --warning: oklch(0.80 0.14 78);
  --warning-foreground: oklch(0.20 0.03 78);

  --border: oklch(1 0 0 / 12%);
  --input: oklch(1 0 0 / 16%);
  --ring: oklch(0.68 0.13 258);

  --chart-1: oklch(0.68 0.13 258);
  --chart-2: oklch(0.72 0.12 196);
  --chart-3: oklch(0.70 0.13 156);
  --chart-4: oklch(0.80 0.14 78);
  --chart-5: oklch(0.70 0.16 320);

  --sidebar: oklch(0.22 0.014 258);
  --sidebar-foreground: oklch(0.96 0.005 258);
  --sidebar-primary: oklch(0.68 0.13 258);
  --sidebar-primary-foreground: oklch(0.18 0.012 258);
  --sidebar-accent: oklch(0.30 0.03 258);
  --sidebar-accent-foreground: oklch(0.96 0.005 258);
  --sidebar-border: oklch(1 0 0 / 12%);
  --sidebar-ring: oklch(0.68 0.13 258);
}

@theme inline {
  --font-sans: 'Pretendard Variable', Pretendard, system-ui, -apple-system, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;

  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-success: var(--success);
  --color-success-foreground: var(--success-foreground);
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);

  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
}

@layer base {
  * { @apply border-border outline-ring/50; }
  body { @apply bg-background text-foreground; font-feature-settings: 'ss01', 'tnum' 0; }
  .tabular { font-variant-numeric: tabular-nums; }
}
```

### 7.3 아이덴티티 정의

| 요소 | 값 | 근거 |
| --- | --- | --- |
| Primary | `oklch(0.51 0.15 258)` — 딥 인디고블루 | 발주사 관리 도구의 신뢰감. zinc 중립 베이스와 대비가 충분하고 다크에서 `0.68` 로 올려 대비 4.5:1 이상 유지 |
| 차트 팔레트 | 인디고 → 시안 → 그린 → 앰버 → 퍼플 5색 | 색상환에서 최소 40° 간격. 색맹 사용자도 명도 차로 구분 가능 |
| Radius | `0.625rem` (shadcn new-york 기본) | 기본값 유지 |
| 폰트 | Pretendard Variable(로컬 번들, `public/fonts`) → system-ui 폴백 | 한국어 산출물명·조직명 가독성. CDN 링크를 두지 않는다 |
| 숫자 | KPI·테이블 수치는 `.tabular` 클래스 | 자릿수 흔들림 방지 |
| 밀도 | 기본 `text-sm`, 테이블 행 높이 `h-11`, 카드 패딩 `p-6` / 위젯 카드 `p-4` | 운영 화면 정보 밀도 |
| 간격 | Tailwind 기본 4px 스케일. 페이지 좌우 `px-6`, 섹션 간 `gap-6`, 그리드 margin `[16,16]` | 그리드 margin 과 페이지 gap 을 16px 로 일치 |

### 7.4 상태 → 토큰 매핑 (`standard/statusLabels.ts`)

| 도메인 상태 | 라벨 | Badge variant / 토큰 |
| --- | --- | --- |
| `work_product`: none | 없음 | `outline` + `text-muted-foreground` |
| `work_product`: draft | 작성중 | `secondary` |
| `work_product`: submitted | 제출 | `bg-warning text-warning-foreground` |
| `work_product`: approved | 승인 | `bg-success text-success-foreground` |
| `work_product`: rejected | 반려 | `destructive` |
| `project`: planning / active / closing / closed | 준비 / 진행 / 종료중 / 종료 | `outline` / `default` / `bg-warning` / `secondary` |
| `sync_job`: queued / running / succeeded / failed / cancelled | 대기 / 진행 / 성공 / 실패 / 취소 | `outline` / `default`(pulse) / `bg-success` / `destructive` / `secondary` |
| `requirement`: defined→accepted | 정의 / 설계 / 구현 / 검증 / 인수 | 5단계 모두 `outline`, 진행도는 `Progress` 로 표현 |
| `correction_action`: open / done / overdue | 열림 / 완료 / 지연 | `outline` / `bg-success` / `destructive` |
| `risk` severity | 낮음 / 보통 / 높음 | `outline` / `bg-warning` / `destructive` |

색만으로 상태를 구분하지 않는다. Badge 는 항상 텍스트 라벨을 포함한다.

---

## 8. 다음 단계로 넘기는 확정 사항

| 항목 | 넘기는 곳 |
| --- | --- |
| §1.2·§2 의 API 경로·요청/응답 record 시그니처 확정 | `03-api-spec` |
| `WidgetDataset` 봉투를 서버 응답 DTO 로 확정(`columns[].role` enum 포함) | `03-api-spec`, 시맨틱 레이어 설계 |
| SSE 프레임 4종의 서버 측 `SseEmitter` 발행 규격 | `03-api-spec`, `05-ai-pipeline` |
| `GET /api/standard/enums` 응답(22종·활동·상태값) — 프론트 enum 일치 테스트 원천 | `02-data-model`, `03-api-spec` |
| `GET /api/semantic/widget-templates`, `/promotion-targets` 카탈로그 응답 | 시맨틱 레이어 설계 |
