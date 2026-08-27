# 07. 종단 통합 테스트 검출력 검증 (뮤테이션)

통과하는 테스트는 아무것도 증명하지 않는다. 프로덕션 코드에 과거 실제로 났던 결함을
하나씩 주입하고, 테스트 스위트가 실제로 실패하는지로 검출력을 측정했다.

- 대상 스위트: `backend/src/test` 전체 (`./gradlew cleanTest test`)
- 절차: 주입 → `cleanTest test` → 실패 테스트명 기록 → 원복 → 다음 뮤테이션
- 기준선: 14 클래스 / 58 테스트 / 실패 0
- 최종: 15 클래스 / **61 테스트 / 실패 0**
- 결과: **6 / 6 검출** (사각지대 1건은 신규 테스트로 폐쇄 후 재검증)

## 뮤테이션 결과

| # | 뮤테이션 | 주입 위치 | 기대 | 실제 | 잡힘 | 사각지대 조치 |
|---|---|---|---|---|---|---|
| M1 | `allowedProjectIds` 가 역할과 무관하게 전체 프로젝트 반환 | `auth/security/ProjectAccessResolver.java:35` — `switch (p.role())` 전체를 `query("select id from project", Map.of())` 로 치환 | 권한 격리 실패 | **6건 실패**: `AccessIsolationFlowTest.contractorCannotReadUnassignedProject`, `ProjectAccessIsolationTest.contractorSeesOnlyAssignedProjects`, `.contractorCannotRequireUnassignedProject`, `.contractorRequestingUnassignedProjectScopeIsDenied`, `.contractorAggregateExcludesUnassignedProjectRows`, `RoleForbiddenMappingTest.contractorStillReachesConnections` | 잡힘 | 불필요 |
| M2 | `AccessDeniedException` 핸들러 제거 (403 → 500 폴백) | `common/error/GlobalExceptionHandler.java:50-54` 메서드 삭제 | 403 대신 500 | **3건 실패**: `AccessIsolationFlowTest.contractorProjectCreateIsForbiddenNotInternalError`, `RoleForbiddenMappingTest.contractorProjectCreateIsForbiddenNotInternalError`, `.superAdminProjectCreateIsForbiddenNotInternalError` | 잡힘 | 불필요 |
| M3 | 프로젝트 생성의 착수일 ≤ 마감일 검증 제거 | `project/service/ProjectService.java:81-83` 가드 삭제 | 400 대신 201 | **2건 실패**: `ClientProjectFlowTest.projectCreateRejectsStartDateAfterEndDate`, `ProjectLifecycleRuleTest.createRejectsStartDateAfterEndDate` | 잡힘 | 불필요 |
| M4 | 대시보드 레이아웃 저장을 no-op 으로 | `dashboard/service/DashboardService.java:105` — `dashboardRepository.updateLayout(...)` 호출 삭제 | 재조회 시 레이아웃 미복원 | **1건 실패**: `AnalyticsFlowTest.dashboardLayoutIsPersistedOnServerAndRestoredOnReread` | 잡힘 | 불필요 |
| M5 | `SemanticQueryBuilder` 의 JOIN dedupe 를 별칭 기준 → 문자열 동일성으로 되돌림 | `semantic/service/SemanticQueryBuilder.java:117` — `joins.putIfAbsent(joinAlias(fragment), fragment)` → `joins.putIfAbsent(fragment, fragment)` | 중복 별칭으로 SQL 실행 오류 | **1차: 실패 0 — 살아남음**<br>2차(신규 테스트 후): **1건 실패** `SemanticJoinDedupeTest.sameAliasJoinedByDifferentClauseTextIsEmittedOnce` | 1차 놓침 → **2차 잡힘** | `SemanticJoinDedupeTest` 신규 추가 (아래 참조) |
| M6 | 프로젝트 종료의 `acceptance_record` 검증 제거 | `project/service/ProjectClosureService.java:75` — `closable = acceptance && wpOk && corrOk` → `wpOk && corrOk` | 검수확인서 없이 종료 허용 | **1건 실패**: `ProjectLifecycleRuleTest.closeIsRejectedWithoutAcceptanceRecord` | 잡힘 | 불필요 (약점은 아래 기록) |

## 사각지대 1: M5 — JOIN 별칭 중복

### 왜 살아남았나
살아남은 원인은 테스트 설계가 아니라 **카탈로그 데이터의 우연**이었다.
현재 시맨틱 카탈로그에서 조인 절을 가진 행은 4개뿐이고, 같은 별칭을 두 번 거는 유일한 쌍은
`contractor_org` 차원과 `contractor_org_id__in` 필터다.

```
D | contractor_org        | left join tool_connection tc on tc.id = e.tool_connection_id left join organization o on o.id = tc.contractor_org_id
F | contractor_org_id__in | left join tool_connection tc on tc.id = e.tool_connection_id
```

차원 절이 조각으로 분해된 뒤의 첫 조각이 필터 절과 **바이트 단위로 동일**하다.
따라서 문자열 키로 dedupe 해도 결과가 같아진다 — 현재 데이터에 한해 뮤테이션이 등가(equivalent)였다.
`SemanticCatalogExhaustiveTest` 가 497조합을 실제 실행해도 이 결함은 드러나지 않는다.

### 위험
카탈로그는 **DB 데이터**다. 마이그레이션으로 조인 절을 한 줄만 추가해도
(공백 차이, `on` 양변 순서 차이, 다른 `on` 조건) 동일 별칭이 두 번 방출되고
Postgres 가 `table name "p" specified more than once` 로 **실행 시점에** 죽는다.
컴파일과 기존 단위 테스트는 전부 통과한다 — 이 프로젝트가 반복해서 당한 결함 유형 그대로다.

### 조치
`backend/src/test/java/kr/co/axlink/semantic/SemanticJoinDedupeTest.java` 신규 추가 (3 테스트).
카탈로그 데이터에 의존하지 않도록 `MeasureDef` / `DimensionDef` 를 직접 조립해
`SemanticQueryBuilder` 를 통과시키고, 생성된 SQL 을 **실제 `axlink_test` 에 실행**한다.

| 테스트 | 검증 대상 |
|---|---|
| `sameAliasJoinedByDifferentClauseTextIsEmittedOnce` | 같은 별칭 `p` 를 서로 다른 문구(`join project p on p.id = e.project_id` vs `LEFT JOIN project p ON e.project_id = p.id`)로 조인 → join 1회 방출 + SQL 실행 성공. **M5 를 죽이는 테스트** |
| `multiJoinClauseIsSplitAndDedupedPerAlias` | 여러 조인이 이어붙은 절이 별칭 단위로 분해·중복 제거되는지 (운영 데이터의 `contractor_org` 형태) |
| `distinctAliasesOnSameTableAreBothKept` | 별칭이 다르면(`p` / `p2`) 같은 테이블이라도 둘 다 유지 — dedupe 가 과잉 제거하지 않는지 |

세 번째 테스트는 dedupe 를 반대 방향으로도 고정한다. 별칭 기준 dedupe 를
"테이블 기준"으로 잘못 조이는 회귀를 막는다.

> 참고: 두 번째 테스트는 M5 하에서도 통과한다(조각 문자열이 동일하므로). 의도된 것으로,
> M5 를 죽이는 책임은 첫 번째 테스트에 있다.

## 사각지대 2 (미조치, 기록만): M6 의 HTTP 계층 테스트가 규칙을 격리하지 못함

M6 는 스위트 전체로는 잡혔지만, **잡은 것은 기존 서비스 계층 테스트**
`ProjectLifecycleRuleTest.closeIsRejectedWithoutAcceptanceRecord` 하나뿐이다.
신규 종단 테스트 `ClientProjectFlowTest.projectCloseIsRejectedWithoutAcceptanceRecord` 는
M6 하에서도 **통과했다** — 즉 이 테스트는 옳은 이유로 초록이 아니다.

원인: 갓 생성한 프로젝트는 표준 산출물 22종이 전부 미승인 상태라
`REQUIRED_WORK_PRODUCTS_APPROVED` 게이트가 이미 false 다.
검수확인서 검증을 없애도 `closable` 은 여전히 false 이므로 409 가 그대로 나온다.
`ProjectLifecycleRuleTest` 는 `approveAllWorkProducts(projectId)` 로 다른 게이트를
먼저 만족시켜 검수확인서 조건만 남기기 때문에 결함을 격리한다.

**미조치 판단 근거**: 규칙 자체는 이미 격리 검증되고 있고, 종단 테스트가 추가로 덮는 것은
컨트롤러 매핑(409 + `CLOSURE_GATE_UNSATISFIED`)뿐인데 그건 현재 테스트가 이미 확인한다.
중복 테스트를 늘리는 대신 약점으로 기록한다.
단, **서비스 계층 테스트를 지우면 M6 가 즉시 무방비가 된다** — `ProjectLifecycleRuleTest`
는 종단 테스트로 대체 가능한 자산이 아니다.

## 부수 관찰

- **M2 가 `ContractorPipelineFlowTest.contractorIsClosedOutOfClientOnlyScreensOfAssignedProject`
  를 실패시키지 않았다.** 해당 403 들은 Spring Security 의 `AccessDeniedException` 이 아니라
  애플리케이션이 직접 던지는 `ApiException(ROLE_FORBIDDEN)` 경로에서 나온다.
  같은 `ROLE_FORBIDDEN` 코드라도 **두 개의 서로 다른 경로**가 존재하며,
  뮤테이션이 그 사실을 드러냈다. 두 경로 모두 테스트로 덮여 있다(M2 가 다른 3건으로 잡힘).
- **M1 이 6건을 실패시켰다** — 권한 격리는 스위트에서 가장 두껍게 덮인 영역이다.
- **M4 는 정확히 1건만 실패시켰다.** 레이아웃 영속화는 단일 테스트에 의존한다.
  얇지만 결함은 확실히 잡히므로 현 상태로 충분하다.

## 재현

```bash
cd backend
./gradlew cleanTest test
```

```
BUILD SUCCESSFUL
15 test classes / 61 tests / 0 failures / 0 errors
```

뮤테이션 주입·원복은 스크립트로 자동화했고, 검증 종료 후 6개 프로덕션 파일 전부를
주입 이전 사본과 바이트 단위 비교(`diff`)해 원복을 확인했다 — 6/6 IDENTICAL.
프로덕션 코드 변경은 **없다**. 추가된 파일은 테스트 1개뿐이다.
