# AX-Link 설계 검증 보고서 (독립 검토)

> **2026-08-21 범위 확정**: 연동 도구는 형상관리 **GitHub** · 프로젝트 관리 **Redmine** 2종으로 확정했다.
> 이 문서의 Jira · GitLab · Notion 관련 서술은 그 시점 이전 기록이며 더 이상 유효하지 않다.
> 현재 범위는 `docs/AX-Link-PRD.md` §1.4 와 `docs/design/02-logical-datamodel.md` §3.5 를 따른다.


| 항목 | 내용 |
| --- | --- |
| 문서 ID | `design/04-design-review` |
| 버전 | v1.0 (2026-08-20) |
| 검토 대상 | PRD + 설계 8문서 + `backend/src/main/resources/db/migration/V1__init.sql` |
| 검토 축 | 요구사항 커버리지 · 계층 정합성 · PRD 6.1.1 금지규칙 · 불변식 강제 · 환경 제약 · 보안 · 구현 가능성 |
| **판정** | **FAIL** — CRITICAL 1건, HIGH 5건 |

---

## 0. 요약

DDL(`V1__init.sql`)·논리 데이터 모델·물리 백엔드 설계 3자는 **거의 완전히 정합**하다. 보안 설계(권한 필터의 쿼리 레이어 강제, 시맨틱 레이어의 카탈로그 화이트리스트, 인증정보 AES-256-GCM 단일 복호화 지점)와 환경 제약 준수(pgvector `vector(1024)` + HNSW, Ollama 단독, Docker 없음, Java 17)는 결함이 없다.

결함은 두 군데에 집중되어 있다.

1. **프론트엔드 계약이 다른 전 계층과 표기 규칙이 다르다.** `03-physical-backend.md` §0 C-2 가 "전 계층 CONSTANT_CASE" 로 충돌을 해소했다고 선언했으나, `03-physical-frontend.md` §4 의 `src/types/api.ts` 전문과 §5.2 렌더러 레지스트리는 정정 전 소문자·케밥 표기를 그대로 담고 있다. 두 문서 모두 "구현 에이전트는 그대로 복사한다" 지위를 갖고 있어 구현 시 반드시 충돌한다.
2. **시맨틱 카탈로그 시드가 조립 골격과 맞지 않는다.** `V1__init.sql` 의 dimension·filter 시드 3건이 `03-physical-backend.md` §5.3 의 SQL 골격으로 조립되면 PostgreSQL 오류가 난다. 카탈로그는 코드 수정 없이 확장한다는 ADR-004 전제상, 이 3건은 배포 후 런타임에서만 드러난다.

---

## 1. 심각도별 발견 사항

### CRITICAL-1 · 프론트 enum 표기가 DB·백엔드와 불일치 (계층 정합성 / 불변식 INV-18)

| 항목 | 내용 |
| --- | --- |
| 위치 | `03-physical-frontend.md` §4 `src/types/api.ts` 전문 (825~890행), §5.2 `renderer-registry.ts` |
| 충돌 상대 | `V1__init.sql` `ck_widget__template`·`ck_requirement__status` 등 전 CHECK 제약, `02-logical-datamodel.md` §3.6, `03-physical-backend.md` §0 C-2·§5.5 |

`03-physical-backend.md` §0 C-2 는 **"API 문서 §3.0 의 소문자·케밥 리터럴은 CONSTANT_CASE 로 정정해 프론트 `standard/` 에 반영한다"** 고 확정했다. 그런데 프론트 물리 설계는 정정 전 값을 그대로 싣고 있다.

| 대상 | 프론트 `types/api.ts` | DB CHECK / Java enum | 결과 |
| --- | --- | --- | --- |
| `WidgetTemplate` | `'stat-card' \| 'bar-chart' \| …` | `STAT_CARD`,`BAR_CHART`,… | **위젯 8종 전부 `UnsupportedWidget` 으로 렌더**. `widgetRenderers['BAR_CHART']` 가 `undefined` |
| `RequirementStatus` | `'defined' \| 'designed' \| …` | `DEFINED`,`DESIGNED`,… | 상태 배지·필터·전이 Dialog 전부 미매칭 |
| `IssueStatus` / `WorkProductStatus` / `RiskStatus` / `ChangeRequestStatus` / `CorrectionActionStatus` | 소문자 | CONSTANT_CASE | 동상 |
| `ProjectStatus` / `UserStatus` / `ConnectionStatus` / `SyncJobStatus` | 소문자 | CONSTANT_CASE | 동상 |
| `TraceLinkKind` | `'designs' \| 'implements' \| …` | `DESIGNS`,`IMPLEMENTS`,… | 추적표 `brokenAt` 판정 실패 |
| `FilterOp` | `'eq'\|'ne'\|'in'\|'not_in'\|'gt'\|'gte'\|'lt'\|'lte'\|'between'\|'in_month'\|'last_n_days'` (11) | `IN,EQ,BETWEEN,IN_MONTH,LAST_N_DAYS,GTE,LTE` (7) | 값·개수 양쪽 불일치. `ne`·`not_in`·`gt`·`lt` 는 DB CHECK 밖 |
| `OrgType` | `'CLIENT'\|'CONTRACTOR'\|'PLATFORM'` | `CLIENT`,`CONTRACTOR` | `ck_organization__type` 위반 값이 타입에 존재 |

백엔드 §5.5 `WidgetDataAssembler` 는 이미 `STAT_CARD`·`BAR_CHART` 로 분기한다. `EnumContractTest`(백엔드 §8.4)는 `frontend/src/standard/*.ts` 만 파싱하므로 `types/api.ts` 의 불일치는 **테스트로도 잡히지 않는다.**

**조치**

1. `03-physical-frontend.md` §4 `src/types/api.ts` 전문의 아래 타입 리터럴을 전부 CONSTANT_CASE 로 교체한다:
   `UserStatus`, `ProjectStatus`, `ConnectionStatus`, `SyncJobStatus`, `RequirementStatus`, `IssueStatus`, `WorkProductStatus`, `RiskStatus`, `ChangeRequestStatus`, `CorrectionActionStatus`, `Severity`, `Likelihood`, `TraceEntityType`, `TraceLinkKind`, `DocumentStatus`, `WidgetTemplate`, `MappingSourceKind`, `MappingTargetEntity`, `FilterOp`.
   개별 인터페이스 안의 인라인 리터럴도 함께: `AssignmentResponse.status`, `ToolConnectionStatusUpdateRequest.status`, `TraceLinkResponse.origin`/`.status`, `AcceptanceRecordResponse.status`, `MessageResponse.role`/`.feedback`, `MessageSourceResponse.sourceType`, `MessageFeedbackRequest.feedback`, `StructuringDraftResponse.status`, `SemanticMeasureResponse.status`, `WidgetOptions.sort`, `SseDoneEvent.finishReason`.
2. `FilterOp` 를 `'IN'|'EQ'|'BETWEEN'|'IN_MONTH'|'LAST_N_DAYS'|'GTE'|'LTE'` 7종으로 축소한다(`ck_semantic_filter__op` 와 동일).
3. `OrgType` 에서 `'PLATFORM'` 을 제거한다(`03-physical-db.md` §0 이 이미 2종으로 확정).
4. §5.2 `renderer-registry.ts` 의 맵 키를 `STAT_CARD: StatCardWidget, BAR_CHART: …` 로 바꾼다. `resolveWidgetRenderer(template: string)` 시그니처는 유지한다(미지원 값 폴백이 목적).
5. `02-logical-api.md` §3.0 도 같은 값으로 정정한다 — 이 문서가 "백엔드·프론트 병렬 구현의 유일한 계약" 을 자칭하므로 방치하면 재발한다.
6. `EnumContractTest` 대상에 `frontend/src/types/api.ts` 를 추가해 `standard/` 뿐 아니라 DTO 타입 리터럴도 검증한다.

---

### HIGH-1 · `contractor_org_id__in` 필터가 JOIN 없이 `tc` 별칭을 참조 (시맨틱 레이어 런타임 오류)

| 항목 | 내용 |
| --- | --- |
| 위치 | `V1__init.sql` L979 `semantic_filter` 시드, `02-logical-datamodel.md` §7.4 |
| 조립 골격 | `03-physical-backend.md` §5.3 |

```
('contractor_org_id__in', 'contractor_org_id', 'IN', '용역사', '…', 'tc.contractor_org_id', 'UUID_LIST', null)
```

`semantic_filter` 테이블에는 `requires_join` 컬럼이 **없다**. `tc` 별칭은 `semantic_dimension.contractor_org.requires_join` 에서만 생성된다. 그런데 이 필터는 measure 7종(`requirement_fulfillment_rate`, `requirement_test_trace_rate`, `issue_resolution_rate`, `issue_avg_resolution_days`, `open_issue_count`, `code_activity_count`, `test_pass_rate`)의 `allowed_filters` 에 들어 있고, dimension 선택은 독립적이다.

사용자가 "용역사 A의 이슈 처리율" 을 dimension 없이 요청하면 조립 SQL 은
`… FROM issue e WHERE e.project_id = ANY(?) AND tc.contractor_org_id = ANY(?)` 가 되어
`ERROR: missing FROM-clause entry for table "tc"` 로 실패한다. 카탈로그 검증 V1~V7 은 전부 통과하므로 `CATALOG_VALIDATION_FAILED` 가 아니라 500 이 난다.

**조치** — 둘 중 하나를 택한다.

- (권장) `semantic_filter` 에 `requires_join text` 컬럼을 추가하고 `contractor_org_id__in` 행에 `'left join tool_connection tc on tc.id = e.tool_connection_id'` 를 넣는다. `SemanticQueryBuilder` 는 measure·dimension·filter 3원의 JOIN 문자열을 `LinkedHashSet` 으로 dedupe 해 부착한다(§5.3 이 이미 dimension JOIN dedupe 를 규정했으므로 집합에 filter 를 더하기만 하면 된다).
- 또는 `column_expr` 를 `e.tool_connection_id` 로 바꾸고 `value` 를 `contractor_org_id` 가 아니라 `tool_connection_id` 목록으로 받는다. 이 경우 `field` 명과 LLM `description` 도 함께 바꿔야 하고 화면 필터 UX 가 나빠진다.

---

### HIGH-2 · `assignee` dimension 이 `code_change` 에 존재하지 않는 컬럼을 참조

| 항목 | 내용 |
| --- | --- |
| 위치 | `V1__init.sql` L969 (`assignee` dimension), L925 (`code_activity_count.allowed_dimensions`) |

```
('assignee', '담당자', '…', 'coalesce(e.assignee, ''미지정'')', null, null, 'CATEGORY')
'code_activity_count' … allowed_dimensions = '{project,contractor_org,code_change_kind,period_month,period_week,assignee}'
```

`code_change` 테이블에는 `assignee` 컬럼이 없다(`author varchar(200)` 만 있다 — `V1__init.sql` L403). `code_activity_count` 를 `assignee` 로 그룹핑하면 `ERROR: column e.assignee does not exist`.

논리 설계 §7.3 은 `coalesce(e.assignee, e.author, '미지정')` 로 적혀 있었으나, 이 식은 `issue`(=`author` 없음)와 `code_change`(=`assignee` 없음) **양쪽 모두에서 실패**한다. DDL 시드가 `e.author` 를 뺀 것은 `issue` 기준으로는 옳은 정정이지만 `code_change` 를 깨뜨렸다.

**조치** — dimension 을 2개로 분리한다.

| `key` | `select_expr` | 허용 measure |
| --- | --- | --- |
| `assignee` | `coalesce(e.assignee, '미지정')` | `issue_*`, `requirement_*` (base table 에 `assignee` 존재) |
| `author` | `coalesce(e.author, '미지정')` | `code_activity_count`, `test_pass_rate` |

`code_activity_count.allowed_dimensions` 의 `assignee` 를 `author` 로 교체한다. 논리 §7.3 표와 백엔드 `CatalogRegistry.load()` 의 기동 시 참조 무결성 검사에 **"measure 의 base_table 에 dimension 이 참조하는 컬럼이 실재하는가"** 검사를 추가한다(`information_schema.columns` 대조 또는 `explain` 드라이런). 지금 검사는 "키 존재" 만 본다.

---

### HIGH-3 · dimension `label_expr` 가 SELECT 에는 들어가고 GROUP BY 에는 빠진다

| 항목 | 내용 |
| --- | --- |
| 위치 | `03-physical-backend.md` §5.3 SQL 골격, `V1__init.sql` `project`·`contractor_org` dimension 시드 |

골격:

```
SELECT  {d0.selectExpr} AS d0
      [, {d0.labelExpr} AS d0_label]
      , {measure.valueExpr} AS value
 …
 [GROUP BY d0[, d1]]
```

`project` dimension 은 `select_expr = e.project_id::text`, `label_expr = p.name` 이다. 조립 결과:

```sql
SELECT e.project_id::text AS d0, p.name AS d0_label, count(*) AS value
  FROM issue e join project p on p.id = e.project_id
 WHERE e.project_id = ANY(?)
 GROUP BY e.project_id::text
```

→ `ERROR: column "p.name" must appear in the GROUP BY clause or be used in an aggregate function`.

PostgreSQL 의 functional-dependency 예외는 **그 테이블의 PK 로 그룹핑할 때만** 적용된다. 여기서는 자식 테이블의 캐스팅 식으로 그룹핑하므로 해당하지 않는다. `contractor_org`(`label_expr = coalesce(o.name, '미지정')`)도 동일하게 실패한다. 즉 **`project` 또는 `contractor_org` 를 dimension 으로 쓰는 모든 위젯이 실패**하며, 이 둘은 measure 13종 중 12종의 `default_dimension` 이거나 허용 차원이다.

**조치** — §5.3 골격의 `GROUP BY` 를 `label_expr` 를 포함하도록 고친다.

```
 GROUP BY d0[, d0_label][, d1][, d1_label]
```

즉 `labelExpr` 가 `null` 이 아닌 dimension 은 GROUP BY 목록에 select_expr 와 label_expr 를 **둘 다** 넣는다. 문서 §5.3 표에 "labelExpr 가 있으면 GROUP BY 에 동반 부착" 규칙을 명시하고, `SemanticQueryExecutorIT` 에 `project`·`contractor_org` dimension 실행 케이스를 추가한다(§8.2).

---

### HIGH-4 · `DocumentStatus` 가 DB enum 에 없는 값을 갖고, 프론트 폴링이 그 값을 대기한다

| 항목 | 내용 |
| --- | --- |
| 위치 | `02-logical-api.md` §3.0, `03-physical-frontend.md` §4, `03-physical-frontend.md` §3.10 `document-table.tsx` |
| 충돌 상대 | `V1__init.sql` L234 `ck_document_upload__status` |

| 계층 | 값 |
| --- | --- |
| DB / `02-logical-datamodel.md` §3.5 | `UPLOADED`, `EXTRACTED`, `STRUCTURED`, `CONFIRMED`, `REJECTED`, `FAILED` (6) |
| API / 프론트 | `uploaded`, **`extracting`**, `extracted`, **`structuring`**, `structured`, `confirmed`, `rejected`, `failed` (8) |

`extracting`·`structuring` 은 DB 에 저장될 수 없는 값이다. 그런데 `document-table.tsx` 의 책임이 **"`structuring` 상태 행만 2초 폴링"** 으로 확정되어 있다. 서버는 그 값을 절대 반환하지 않으므로 **폴링이 한 번도 시작되지 않고**, 사용자는 업로드 후 정형화 초안 화면으로 전환되지 않는다(UC-11, INT-006 미동작).

**조치**

1. `DocumentStatus` 를 DB 6값 CONSTANT_CASE 로 통일한다: `UPLOADED | EXTRACTED | STRUCTURED | CONFIRMED | REJECTED | FAILED`.
2. `document-table.tsx` 폴링 조건을 `status === 'UPLOADED' || status === 'EXTRACTED'`(= 아직 진행 중) 로 바꾸고, `STRUCTURED` 도달 시 초안 화면 링크를 활성화한다.
3. 진행 단계를 화면에 더 세분해 보여야 한다면 DB 에 값을 추가하는 것이 아니라 `document_upload.status` 6값 + `updated_at` 으로 표시한다. 값을 추가하려면 `ck_document_upload__status` 를 함께 고쳐야 한다.

---

### HIGH-5 · `Severity`·`TraceEntityType` 가 DB 값 집합을 표현하지 못한다

| DTO 필드 | 프론트/API 타입 | DB CHECK | 문제 |
| --- | --- | --- | --- |
| `IssueResponse.severity` | `Severity = 'critical'\|'high'\|'medium'\|'low'` | `ck_issue__severity in ('BLOCKER','CRITICAL','MAJOR','MINOR','TRIVIAL')` | `BLOCKER`·`MAJOR`·`MINOR`·`TRIVIAL` 을 **표현할 수 없다**. `issue_severity` 는 `issue_severity__in` 필터의 `enum_values` 이기도 해서 위젯 필터 UI 가 잘못된 선택지를 그린다 |
| `RiskResponse.severity` | 동일 `Severity` | `ck_risk__severity in ('LOW','MEDIUM','HIGH','CRITICAL')` | 값 집합은 4개로 같으나 표기가 소문자라 미매칭 |
| `RiskResponse.probability`/`impact` | `Likelihood = 'high'\|'medium'\|'low'` | `LOW,MEDIUM,HIGH,CRITICAL` | `CRITICAL` 누락 |
| `TraceLinkResponse.fromType`/`toType`, `TraceLinkCreateRequest` | `TraceEntityType = 'requirement'\|'issue'\|'work_product'` (3) | `ck_trace_link__from_type in ('REQUIREMENT','ISSUE','WORK_PRODUCT','RISK','CODE_CHANGE','CHANGE_REQUEST','CORRECTION_ACTION')` (7) | **`CODE_CHANGE` 를 표현할 수 없다.** 개념 §3.3 의 "MR 제목의 이슈 키로 `TraceLink(implements)` 자동 생성" 은 from 측이 `code_change` 다. 즉 자동 생성된 추적 링크가 API 로 나갈 때 타입 밖 값이 되고, STD-002 추적표의 "구현(MR)" 열이 비어 보인다 |
| `MessageSourceResponse.sourceType` | 6값 소문자 | `ck_message_source__source_type` = `doc_source_type` 9값 | `MEETING_RECORD`·`PROGRESS_RECORD`·`DOCUMENT_UPLOAD` 출처가 타입 밖 |

**조치** — 프론트/API 타입을 DB CHECK 값 집합과 **1:1 동일**하게 재정의한다.

```ts
export type IssueSeverity = 'BLOCKER' | 'CRITICAL' | 'MAJOR' | 'MINOR' | 'TRIVIAL';
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type TraceEntityType =
  | 'REQUIREMENT' | 'ISSUE' | 'WORK_PRODUCT' | 'RISK'
  | 'CODE_CHANGE' | 'CHANGE_REQUEST' | 'CORRECTION_ACTION';
export type DocSourceType =
  | 'WORK_PRODUCT' | 'REQUIREMENT' | 'ISSUE' | 'RISK' | 'CHANGE_REQUEST'
  | 'CORRECTION_ACTION' | 'MEETING_RECORD' | 'PROGRESS_RECORD' | 'DOCUMENT_UPLOAD';
```

`Severity` 라는 공용 별칭은 폐기한다 — `issue_severity` 와 `risk_level` 은 값 집합이 다른 별개 enum 이다. `RiskResponse.probability`/`impact`/`severity` 는 전부 `RiskLevel` 을 쓴다. `standard/labels.ts` 의 `SEVERITY_LABEL` 을 `ISSUE_SEVERITY_LABEL` / `RISK_LEVEL_LABEL` 로 분리한다.

---

## 2. MEDIUM

### MEDIUM-1 · 매핑 규칙 모델이 계층마다 다르다 (구현 가능성)

| 계층 | 모델 |
| --- | --- |
| `02-logical-datamodel.md` §1·§5.2, `V1__init.sql` | `tool_connection.mapping_rules_json` **jsonb**. 규칙에 id 없음. `sourceKind` = `JIRA_ISSUE_TYPE`/`JIRA_STATUS_CATEGORY`/`GITLAB_OBJECT_KIND`/`GITLAB_STATE`. `targetEntity` = `REQUIREMENT`/`ISSUE`/`RISK`/`WORK_PRODUCT`/`CODE_CHANGE`/`PROGRESS_RECORD`/`IGNORE` |
| `02-logical-api.md` §3.5·§7.2 | `MappingRuleResponse { id, connectionId, … }` — **행 id 를 가진 테이블 전제**. 시퀀스에도 `insert mapping_rule × detectedItemTypes` |
| `03-physical-frontend.md` §4 | `MappingSourceKind = 'ISSUE_TYPE'\|'OBJECT_KIND'\|'TRACKER'`, `MappingTargetEntity` 에 `'trace_link'` 포함·`CODE_CHANGE`/`IGNORE` 누락 |
| `03-physical-backend.md` §2.11 | `MappingRules(int version, List<MappingRule>)` — jsonb. `MappingSourceKind` enum 은 데이터모델 값 |

`TRACKER` 는 Redmine 용이고 본 범위(Jira·GitLab)에 해당 없다. `trace_link` 는 매핑 규칙의 target 이 아니라 승격 부산물이다(개념 §3.3).

**조치**: jsonb 모델로 통일한다. `MappingRuleResponse` 에서 `id` 를 제거하고 `index: number`(배열 순번)로 바꾸거나, `PUT` 전체 치환 API 만 있으므로 응답을 `MappingRuleUpsertRequest[]` 와 동일 형태로 맞춘다. `sourceKind` 는 4값, `targetEntity` 는 7값(`IGNORE` 포함)으로 프론트 타입을 교체하고, `02-logical-api.md` §7.2 시퀀스의 `insert mapping_rule` 을 `update tool_connection set mapping_rules_json = …` 로 정정한다.

### MEDIUM-2 · 업로드 크기 상한이 50MB / 100MB 로 갈린다

| 계층 | 값 |
| --- | --- |
| `02-logical-api.md` §1.8·§1.5(`PAYLOAD_TOO_LARGE`), `application.yml` `max-file-size: 50MB`, 프론트 `upload-dropzone.tsx`("50MB 사전 차단") | 50MB |
| `02-logical-datamodel.md` §2.3, `V1__init.sql` `ck_document_upload__size … <= 104857600` | 100MB |

**조치**: 50MB 로 통일한다(멀티파트 상한이 실질 게이트다). `ck_document_upload__size` 를 `<= 52428800` 으로 바꾸는 마이그레이션을 V2 에 넣거나, DB CHECK 를 100MB 로 남기되 "애플리케이션 상한 50MB, DB 는 여유 상한" 임을 `02-logical-datamodel.md` §2.3 에 1줄로 명시한다. 지금은 두 값이 근거 없이 다르다.

### MEDIUM-3 · 에러 코드 집합이 API 문서와 DB CHECK 사이에서 다르다

`ck_sync_job__error_code` 는 11값이고 `02-logical-api.md` §1.5 는 24값이다. 겹치지 않는 지점:

| 코드 | API §1.5 | `ck_sync_job__error_code` |
| --- | :-: | :-: |
| `TOOL_UNREACHABLE` (502) | ✅ | — |
| `TOOL_UNAVAILABLE` | — | ✅ |
| `TOOL_RATE_LIMITED` | — | ✅ |
| `AI_TOOL_CALL_FAILED` (502) | ✅ | — |
| `EMBEDDING_DIMENSION_MISMATCH` | — | ✅ |

동기화 실패가 rate limit 로 끝났을 때 서비스가 `TOOL_RATE_LIMITED` 를 `sync_job.error_code` 에 쓰는데, `ErrorCode` Java enum 에 그 값이 없으면 컴파일 시점에 드러나지 않고 응답 매핑에서 갈라진다.

**조치**: `kr.co.axlink.common.error.ErrorCode` 를 **합집합**으로 확정하고, `02-logical-api.md` §1.5 표에 `TOOL_RATE_LIMITED`(429/502), `TOOL_UNAVAILABLE`, `EMBEDDING_DIMENSION_MISMATCH`(500) 3행을 추가한다. `TOOL_UNREACHABLE` 과 `TOOL_UNAVAILABLE` 은 같은 뜻이므로 **하나만 남긴다**(`TOOL_UNREACHABLE` 권장, API 문서가 HTTP 매핑까지 정의했다). `ck_sync_job__error_code` 를 그에 맞춰 교체한다.

### MEDIUM-4 · `02-logical-frontend.md` §1.2 의 API 경로 다수가 `02-logical-api.md` 에 없다

| `02-logical-frontend.md` 표기 | `02-logical-api.md` 실제 |
| --- | --- |
| `POST /api/auth/invitations/{token}/accept` | `POST /api/auth/invitations/accept` (token 은 바디) |
| `GET /api/projects?scope=mine` | `scope` 파라미터 없음 |
| `GET /api/projects/{id}/summary` | 없음 (`GET /api/projects/{id}` 의 `metrics`) |
| `GET /api/projects/{id}/dashboards` | `GET /api/dashboards?projectId=` |
| `GET /api/organizations/{oid}/users` | `GET /api/users?organizationId=` |
| `GET /api/projects/{id}/sync-jobs` | `GET /api/sync-jobs?projectId=` |
| `POST /api/qna/messages` | `POST /api/conversations/{conversationId}/messages` |
| `GET /api/projects/{id}/work-products/{type}` | `GET /api/work-products/{workProductId}` |
| `POST /api/users/{uid}/invite` | `POST /api/users/{userId}/invitation-resend` |
| `GET /api/audit-entries` | `GET /api/entity-history` |

`02-logical-api.md` 가 "여기 없는 엔드포인트는 만들지 않는다" 를 선언했으므로 프론트 문서 쪽이 낡았다.

**조치**: `02-logical-frontend.md` §1.2 "데이터 의존 API" 열을 `02-logical-api.md` §2 전수표의 경로로 일괄 교체한다. 특히 `POST /api/qna/messages` 는 SSE 계약(§4)의 경로와 다르므로 반드시 고친다.

### MEDIUM-5 · 용역사 할당 화면(PRJ-003/PRJ-004)의 마운트 지점이 미확정

`03-physical-frontend.md` §3.10 은 `features/assignments/` 4파일(`assignment-sheet.tsx`, `assignment-table.tsx`, `contractor-picker.tsx`, `permission-toggles.tsx`)을 정의하지만, §3.11 라우트 트리에 `assignments` 경로가 없고 어느 페이지가 이들을 호스트하는지 명시되지 않았다. `project-overview-page.tsx` 책임이 "할당·연결 요약" 이라 추정될 뿐이다. `02-logical-frontend.md` 는 `/p/:projectId/assignments` 라우트를 갖고 있어 두 문서가 갈린다.

같은 문제가 매핑 규칙 편집에도 있다 — 논리는 `/p/:projectId/connections/:connectionId` 라우트, 물리는 `connections-page.tsx` 안의 `mapping-rules-dialog.tsx`.

**조치**: 물리 설계 기준으로 §3.11 라우트 트리에 `assignments → AssignmentsPage` 를 추가하거나(권장 — PRD §6.2 가 Sheet + Table 조합의 독립 화면을 전제), `project-overview-page.tsx` 책임 서술에 "`AssignmentTable` + `AssignmentSheet` 호스트" 를 명시한다. `02-logical-frontend.md` §1.2 의 두 라우트도 그 결론에 맞춘다.

### MEDIUM-6 · 위젯 템플릿 닫힌 유니온이 프론트 계약에 남아 있다 (PRD 6.1.1 / INV-28)

`02-logical-frontend.md` §3.2 는 `export type WidgetTemplateId = string`, §3.3 은 `Record<string, WidgetRenderer>` 로 **의도적으로 유니온을 배제**했다. `03-physical-frontend.md` §4 는 `WidgetTemplate` 8종 닫힌 유니온을 선언하고 §5.2 에서 `Record<WidgetTemplate, WidgetRenderer>` 를 맵 타입으로 쓴다.

`resolveWidgetRenderer(template: string)` 폴백이 있어 런타임은 죽지 않지만, 템플릿을 9번째로 추가하면 `types/api.ts`(유니온) + `renderer-registry.ts`(맵) + `template-catalog.ts` 3곳을 동시에 고쳐야 한다 — ax-pms 실패 패턴의 축소판이다.

**조치**: 맵 타입을 `Record<string, WidgetRenderer>` 로 되돌린다. `WidgetTemplate` 유니온은 **마법사 1단계 선택지 타입으로만** 남기고(`WIDGET_TEMPLATES` 카탈로그에서 파생), `WidgetSpec.template` 필드 타입은 `string` 으로 둔다. 서버 검증(V1)이 실질 게이트다.

### MEDIUM-7 · ADM-002 초대 메일 발송이 구현 범위에서 빠졌다

PRD ADM-002 는 "초대 메일 + 최초 비밀번호 설정 링크" 를 명세하고 `01-conceptual-architecture.md` §1.2 EXT-7 이 `spring-boot-starter-mail` SMTP 를 외부 인터페이스로 확정했다. `03-physical-backend.md` §2.9 는 `InvitationSender` 를 **"1차는 메일 발송 대신 `log.info` 로 수락 URL 을 남긴다"** 로 축소하고 `build.gradle` 에 mail 의존성이 없다.

로컬 SMTP 릴레이가 없는 환경 제약을 고려하면 합리적이나, **PRD 요구 미충족이 어느 문서에도 결정으로 기록되지 않았다**(ADR 없음). EXT-7 은 여전히 살아 있다고 적혀 있어 두 문서가 모순이다.

**조치**: `01-conceptual-architecture.md` §1.2 의 EXT-7 을 "1차 범위 밖" 으로 표기하고 ADR-012(초대 메일 유보)를 추가하거나, `spring-boot-starter-mail` 을 의존성에 넣고 `axlink.mail.*` 설정을 `application.yml` 에 추가한다. 어느 쪽이든 `InvitationSender` 인터페이스는 그대로 두어 교체가 1클래스로 끝나게 한다.

### MEDIUM-8 · Flyway 마이그레이션 파일 구성이 3문서에서 다르다

| 문서 | 표기 |
| --- | --- |
| `02-logical-datamodel.md` §9 | `V1__extensions.sql` ~ `V10__history_grants.sql` (10파일) |
| `03-physical-backend.md` §1.1 모듈 레이아웃 | `V1__extensions.sql ... V10__history_grants.sql` |
| `03-physical-db.md` §0, 실제 리포지토리 | **`V1__init.sql` 단일 파일** |
| `03-physical-backend.md` §8.5 픽스처 | "카탈로그 = Flyway `V9__semantic_seed.sql` 그대로" |

**조치**: `V1__init.sql` 단일 파일이 실측 검증까지 끝난 결론이므로 이것을 기준으로 `02-logical-datamodel.md` §9 표를 "V1 단일 파일 + V2 이후 변경 단위" 로 교체하고, `03-physical-backend.md` §1.1·§8.5 의 `V1__extensions`·`V9__semantic_seed` 표기를 `V1__init.sql` 로 정정한다.

---

## 3. LOW

| # | 항목 | 내용 · 조치 |
| --- | --- | --- |
| L-1 | INT-003 Webhook 발급 미구현 | ADR-008 에서 명시적으로 유보했고 `tool_connection.webhook_secret_encrypted` 컬럼·`sync_job.kind=WEBHOOK` 값을 예약해 두었다. 공통 컨텍스트 범위(폴링 기반)와도 일치하므로 결함이 아니다. **다만 PRD §2.3·§2.4 의 "데이터 신선도 ≤ 5분(Webhook 기준)" 목표가 15분으로 완화된 사실은 PRD 기대효과 표(§1.3)와 어긋난다** — PRD 측 목표치를 15분으로 정정하거나 ADR-008 영향란에 명시적으로 연결한다 |
| L-2 | Notion·Redmine 커넥터 미구현 | PRD §1.4 In 범위이나 공통 컨텍스트가 Jira·GitLab 으로 한정했다. `tool_type` enum 에 값만 예약(데이터모델 §3.5). 의도된 축소 |
| L-3 | 카탈로그 시드 행수 표기 불일치 | `02-logical-datamodel.md` §1 표는 dimension 11 / filter 14, §9 는 17 / 17, 실제 DDL 은 17 / 17. `03-physical-db.md` §0 이 정정했으나 논리 문서 §1·§7.3·§7.4 의 "전수" 표제가 그대로다. 논리 문서 §1 표를 17/17 로 고치고 §7.3 표제를 "17행", §7.4 를 "17행" 으로 바꾼다 |
| L-4 | 시드 계정 평문 비밀번호가 설계 문서에 상수로 존재 | `03-physical-db.md` §10.2 에 `Axlink!2026` 평문 + bcrypt 해시 3건. 문서에 "운영 배포 전 교체" 경고가 있으나, `V1__init.sql` 이 리포지토리에 커밋되므로 해시가 영구히 이력에 남는다. **조치**: 시드 계정 3건을 `V1__init.sql` 이 아니라 `db/seed/dev-accounts.sql`(Flyway 미관리, 로컬에서 수동 실행)로 분리하거나, 최소한 비밀번호를 환경변수 기반으로 기동 시 주입하는 `DevSeedRunner`(`@Profile("dev")`)로 옮긴다 |
| L-5 | `features/ask` vs `features/ax-query` | `02-logical-frontend.md` §5.4 는 `features/ask/`, `03-physical-frontend.md` §3.10 과 PRD §6.3 은 `features/ax-query/`. PRD 기준 `ax-query` 로 통일하고 논리 문서를 정정 |
| L-6 | `ProjectSummaryResponse.currentSiPhase` 가 non-null | DB `project.current_si_phase` 는 nullable(`PLANNING` 프로젝트는 `null`). DTO 를 `SiPhase \| null` 로 바꾸거나 서버가 기본값 `SI_1` 을 채운다는 규칙을 명시 |
| L-7 | `WorkProductResponse.siActivity: SiPhase` | `SiPhase` 는 `SI_1`~`SI_6` 이고 `si_activity` 컬럼도 동일 도메인이라 문제없다. 다만 타입 이름이 "프로젝트 현재 단계" 와 "산출물 활동" 두 의미를 겸한다. `Iso29110SiActivity` 별칭을 두면 읽기 쉬워진다 |

---

## 4. 결함 없음으로 확인한 항목

| 검증 축 | 결과 | 근거 |
| --- | --- | --- |
| **환경 제약 — pgvector** | ✅ | `doc_chunk.embedding vector(1024)` + `hnsw (embedding vector_cosine_ops) with (m=16, ef_construction=64)`. `real[]` 대체 구현·자체 코사인 함수 **없음**(ADR-002 가 명시적으로 기각). 폴백 임베딩(`FakeEmbeddingAdapter`)도 1024차원 생성(아키텍처 §3.2, 백엔드 §6.2) |
| **환경 제약 — Docker** | ✅ | Testcontainers 미채택, 로컬 PostgreSQL `axlink_test` 사용(백엔드 §8.2·§1.3). 배포는 Spring Boot 단일 프로세스 |
| **환경 제약 — LLM 공급자** | ✅ | Ollama 어댑터 + Fake 어댑터 2벌만. `AiAdapterCountTest` 로 구현체 수 == 2 강제. Anthropic SDK 는 §0 C-3 에서 명시적으로 기각 |
| **환경 제약 — `format` 파라미터** | ✅ | `LlmPort` 계약에 `format` 필드 없음. `NoFormatParameterTest` 가 `OllamaLlmAdapter` 소스의 `"format"` 리터럴을 금지 (INV-34) |
| **환경 제약 — Java 17** | ✅ | `JavaLanguageVersion.of(17)`, Spring Boot 3.3.13, `java.net.http.HttpClient` + Jackson. Java 21 전용 문법·라이브러리 없음(`spring.threads.virtual.enabled: false` 로 가상 스레드도 끔) |
| **보안 — SQL 인젝션** | ✅ | SQL 문자열에 들어가는 값은 `semantic_measure`/`_dimension`/`_filter` 의 조각 컬럼 3종뿐이며 쓰기 API 가 없다(Flyway 시드 전용). `spec` 의 사용자·LLM 문자열은 **키 조회에만** 쓰이고 `ValidatedSpec` 이 카탈로그 객체 참조를 담아 하류로 넘긴다. `LAST_N_DAYS` 도 `make_interval(days => :pN)` 로 정수 바인딩. `NoSqlConcatenationTest` 로 강제 |
| **보안 — 권한 필터** | ✅ | `SemanticQueryBuilder.build(spec, allowedProjectIds)` / `HybridSearchRepository.search(…, projectIds, …)` 가 시그니처로 인자를 강제하고 `WHERE` 첫 조건에 무조건 부착. `ProjectScopeParameterTest`(ArchUnit)가 오버로드 추가를 차단. RAG 프롬프트에 project_id 를 넣지 않음 (INV-04) |
| **보안 — 권한 확장 차단** | ✅ | `resolveScope()` 가 교집합만 반환하고 공집합이면 403. `conversation.project_scope`·`spec.query.projectScope` 는 표시·기본값일 뿐 실행 시 재축소 (INV-25) |
| **보안 — 비밀정보** | ✅ | `auth_encrypted` 는 암호문 컬럼만 존재하고 평문 컬럼이 없다. 응답 DTO 는 `credentialMasked` 만. 복호화는 `ToolConnectionSecretProvider` 단일 지점. Refresh 토큰은 DB 에 SHA-256 만, 재사용 감지 시 전 토큰 폐기. 비밀번호 bcrypt(10) (INV-06) |
| **보안 — 존재 노출** | ✅ | 단건 조회는 권한 실패를 404 로 변환, 프로젝트 리소스 자체만 403 (API §1.5, 백엔드 §3.4 경계규칙 3) |
| **불변식 — INV-11 (22종)** | ✅ | `ck_work_product__type` 22값 + `ck_structuring_draft__proposed_type` + 정형화 확정 시 `WorkProductType.valueOf` 실패 → `WORK_PRODUCT_TYPE_REJECTED`. `03-physical-db.md` §9.3 에서 `NOT_A_TYPE` insert 거부 실증 |
| **불변식 — INV-12 (22행 상시)** | ✅ | `uq_work_product__current (project_id, type) where is_current` + UC-03 22행 bulk insert + 일 1회 보충 배치. 데모 시드 22행 실측 |
| **불변식 — INV-29 (1024차원)** | ✅ | `vector(1024)` 컬럼이 3차원 insert 를 거부함을 실측. `EmbeddingDimensionVerifier` 가 `pg_attribute.atttypmod` 와 `EmbeddingPort.dimension()` 대조 후 불일치 시 기동 실패 |
| **불변식 — INV-17 / INV-22 / INV-08 / INV-14** | ✅ | 부분 유니크 인덱스·CHECK 로 DB 레벨 강제. `03-physical-db.md` §9.3 에서 4건 거부 실증 |
| **불변식 — INV-16 (이력 불변)** | ✅ | `revoke update, delete on entity_history from axlink_app` (V1 §11 `do` 블록). 롤 미존재 시 스킵하는 설계도 타당하되, `03-physical-db.md` §11 이 인프라 인계 사항으로 명시 |
| **금지규칙 — localStorage 레이아웃** | ✅ | `dashboard.layout_json` 단일 원천. ESLint `no-restricted-globals`/`no-restricted-properties` 로 `localStorage` 를 코드 레벨 차단(`03-physical-frontend.md` §1.7). `sessionStorage` 는 refresh 토큰 전용이며 레이아웃과 무관 |
| **금지규칙 — 다층 조립 간접화** | ✅ | 렌더 경로가 `spec.template → resolveWidgetRenderer → <Renderer spec data />` 1단계. 중간 compose 계층 없음 |
| **금지규칙 — 프론트 목업 데이터** | ✅ | MSW 미채택, 목업 파일 없음. 테스트는 `globalThis.fetch` 를 `vi.fn()` 으로 대체 |
| **금지규칙 — shadcn 이외 컴포넌트** | ✅ | `package.json` 의 UI 의존성은 전부 shadcn 프리미티브(`radix-ui`, `cmdk`, `sonner`, `react-day-picker`, `lucide-react`) 또는 ADR-009 예외 기능 라이브러리(`react-grid-layout`, `recharts`). MUI/Ant 류 없음 |
| **요구사항 커버리지 — ADM/PRJ/INT/QNA/STD** | ✅(2건 예외) | ADM-001·002(002 는 MEDIUM-7), PRJ-001~005, INT-001·002·004·005·006(003 은 L-1), QNA-001~006, STD-001~004 전부 엔드포인트·화면·테이블이 대응한다. PRD §4 가 DSH 에는 개별 ID 를 부여하지 않았으며 §4.3 의 레이아웃·3단계 마법사·시맨틱 레이어·템플릿 8종은 전부 설계에 존재한다 |

---

## 5. 재검토 통과 조건

| 순서 | 조치 | 대상 파일 |
| --- | --- | --- |
| 1 | CRITICAL-1 — 프론트 enum 전면 CONSTANT_CASE 정정 + 렌더러 맵 키 교체 + `02-logical-api.md` §3.0 동기화 | `03-physical-frontend.md`, `02-logical-api.md` |
| 2 | HIGH-1 — `semantic_filter.requires_join` 컬럼 추가 + `contractor_org_id__in` 시드 갱신 + 빌더 JOIN dedupe 집합에 filter 포함 | `V1__init.sql`, `02-logical-datamodel.md` §2.5·§7.4, `03-physical-backend.md` §5.3 |
| 3 | HIGH-2 — `author` dimension 신설, `code_activity_count`·`test_pass_rate` 의 `assignee` 를 `author` 로 교체, `CatalogRegistry` 기동 검증에 컬럼 실재 확인 추가 | `V1__init.sql`, `02-logical-datamodel.md` §7.3, `03-physical-backend.md` §5.1 |
| 4 | HIGH-3 — `GROUP BY` 에 `label_expr` 동반 부착 규칙 명시 + 통합 테스트 케이스 추가 | `03-physical-backend.md` §5.3·§8.2, `02-logical-datamodel.md` §7.1 |
| 5 | HIGH-4 — `DocumentStatus` 6값 통일 + 폴링 조건 정정 | `03-physical-frontend.md` §4·§3.10, `02-logical-api.md` §3.0 |
| 6 | HIGH-5 — `IssueSeverity`/`RiskLevel`/`TraceEntityType`/`DocSourceType` 를 DB 값 집합과 1:1 재정의 | `03-physical-frontend.md` §4, `02-logical-api.md` §3.0·§3.7 |
| 7 | MEDIUM 1~8 반영 | 각 표 참조 |

CRITICAL·HIGH 6건이 해소되면 PASS 로 재판정 가능하다. MEDIUM 은 구현 착수와 병행 가능하나 **MEDIUM-1(매핑 규칙)·MEDIUM-4(API 경로)** 는 병렬 구현 시 충돌 지점이므로 착수 전에 정리하는 편이 싸다.
