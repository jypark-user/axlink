# AX-Link 물리 설계 — PostgreSQL 스키마 및 DDL

| 항목 | 내용 |
| --- | --- |
| 문서 ID | `design/03-physical-db` |
| 버전 | v1.0 (2026-08-20) |
| 상위 문서 | `design/02-logical-datamodel.md`, `design/02-logical-api.md` |
| 산출물 | `backend/src/main/resources/db/migration/V1__init.sql` |
| 검증 상태 | **PostgreSQL 14.18 (Homebrew, aarch64) + pgvector 0.8.0 에서 무오류 실행 확인** (§7) |
| 지위 | DDL 파일이 물리 스키마의 유일한 원천. 본 문서는 그 근거·운영 절차를 기술한다 |

---

## 0. 논리 설계 대비 확정 사항

| 항목 | 논리 설계 | 물리 확정 | 근거 |
| --- | --- | --- | --- |
| 마이그레이션 분할 | `V1__extensions` ~ `V10__history_grants` 10파일 | **`V1__init.sql` 단일 파일** | 아직 배포된 환경이 없다. 초기 스키마는 한 번에 적용되므로 파일을 10개로 쪼개면 실행 순서 의존만 늘고 얻는 것이 없다. V2 이후부터 변경 단위로 파일을 나눈다 |
| `entity_history` 권한 회수 | `V10` 에서 `revoke` | V1 §11 의 `do $$ ... $$` 블록. 롤 `axlink_app` 이 존재할 때만 실행 | 롤 생성은 인프라 프로비저닝 책임이고, DDL 은 롤 유무와 무관하게 성공해야 한다 |
| `org_type` 에 `PLATFORM` | `02-logical-api-core` §1.2 JWT 클레임 예시에 `PLATFORM` 등장 | **`CLIENT` / `CONTRACTOR` 2종만** | `02-logical-datamodel` §3.1 이 DDL 의 유일한 근거로 선언되어 있다(문서 헤더). SUPER_ADMIN 은 `ck_app_user__role_org` 검증에서 애초에 조직 타입 대조 대상이 아니므로(§2.1 각주) 운영본부 조직을 `CLIENT` 로 두어도 불변식이 깨지지 않는다. `PLATFORM` 이 실제로 필요해지면 CHECK 제약 한 줄 교체로 끝난다(§1 의 varchar+CHECK 채택 이유) |
| `semantic_dimension` 행수 | §1 표는 11, §9 는 17 | **17행** | §7.3 본표 11행 + "추가 3행" 표제 아래 실제 6행. §9 의 17 이 실측값과 일치 |
| `semantic_filter` 행수 | §1 표는 14, §9 는 17 | **17행** | §7.4 본표 14행 + 기간 필터 3행 |

---

## 1. enum 저장 방식 — `varchar(40)` + `CHECK` (네이티브 enum 미채택)

논리 설계 §0.4 를 그대로 물리 구현했다. 근거를 재확인한다.

| 축 | 네이티브 `create type ... as enum` | `varchar(40)` + `CHECK` |
| --- | --- | --- |
| 값 추가 | `alter type ... add value` — **트랜잭션 내에서 같은 타입을 즉시 사용할 수 없다**(PG 14). Flyway 마이그레이션이 "값 추가 → 그 값으로 UPDATE" 를 한 파일에 담지 못한다 | `alter table ... drop constraint` + `add constraint` 2줄. 같은 트랜잭션에서 즉시 사용 가능 |
| 값 제거·개명 | 사실상 불가. 타입 재생성 + 전 컬럼 캐스팅 | 제약 교체 1회 |
| 값 순서 변경 | `alter type ... add value before/after` 로 제한적 | 순서 개념이 없다. 정렬은 애플리케이션·`case` 식 책임 |
| JPA 매핑 | `@Enumerated` + 커스텀 `UserType`/`@JdbcTypeCode` 필요 | `@Enumerated(EnumType.STRING)` 만으로 매핑 |
| 강제력 | DB 레벨 거부 | **동일하게 DB 레벨 거부** (INV-11 충족, §7 검증 3에서 실증) |
| 검사 비용 | 타입 검사 | `IN` 리스트 검사. 22종에서도 무시 가능 |

값 목록이 22종으로 가장 긴 `work_product_type` 도 최장 값이 `PRODUCT_OPERATION_GUIDE`(23자)라 `varchar(40)` 안에 들어온다. `error_code` 최장값 `EMBEDDING_DIMENSION_MISMATCH`(28자)도 동일.

**대가**: 22종 값 목록이 DDL 안에 2회(`ck_work_product__type`, `ck_structuring_draft__proposed_type`) + 시드 1회(`semantic_filter.enum_values`) 등장한다. 이 중복은 INV-18 3자 일치 테스트(Java enum ↔ DB CHECK ↔ 프론트 `standard/`)가 잡는다.

---

## 2. 물리 테이블 목록 (32개)

컨텍스트: IAM 5 · PRJ 1 · INT 4 · STD 12 · INS 5 · KNW 5.

| # | 테이블 | 컨텍스트 | PK 기본값 | 공통열 | 비고 |
| --- | --- | --- | --- | --- | --- |
| 1 | `organization` | IAM | `gen_random_uuid()` | 전체 | |
| 2 | `app_user` | IAM | 〃 | 전체 | 이메일 유일성은 `lower(email)` 표현식 인덱스 |
| 3 | `user_invitation` | IAM | 〃 | 전체 | |
| 4 | `refresh_token` | IAM | 〃 | `id`,`created_at` | 회전 시 신규 insert |
| 5 | `project_assignment` | IAM | 〃 | 전체 | |
| 6 | `project` | PRJ | 〃 | 전체 | CHECK 4종 |
| 7 | `tool_connection` | INT | 〃 | 전체 | `auth_encrypted` 는 암호문만 |
| 8 | `sync_job` | INT | 〃 | 전체 | 자기참조 FK |
| 9 | `raw_artifact` | INT | 〃 | `id`,`created_at` | append/upsert |
| 10 | `document_upload` | INT | 〃 | 전체 | |
| 11 | `work_product` | STD | 〃 | 전체 + 연동 4열 | 22종 CHECK |
| 12 | `requirement` | STD | 〃 | 전체 + 연동 4열 | |
| 13 | `issue` | STD | 〃 | 전체 + 연동 4열 | |
| 14 | `risk` | STD | 〃 | 전체 + 연동 4열 | `severity` 비정규화 |
| 15 | `code_change` | STD | 〃 | 전체 + 연동 4열 | |
| 16 | `trace_link` | STD | 〃 | 전체 | 다형 참조(FK 없음) |
| 17 | `change_request` | STD | 〃 | 전체 | |
| 18 | `correction_action` | STD | 〃 | 전체 | |
| 19 | `progress_record` | STD | 〃 | 전체 + 연동 4열 | |
| 20 | `meeting_record` | STD | 〃 | 전체 | |
| 21 | `acceptance_record` | STD | 〃 | 전체 | 프로젝트당 `ISSUED` 1건 |
| 22 | `entity_history` | STD | 〃 | `id`,`created_at` | append-only |
| 23 | `semantic_measure` | INS | 〃 | 전체 | 시드 13행 |
| 24 | `semantic_dimension` | INS | 〃 | 전체 | 시드 17행 |
| 25 | `semantic_filter` | INS | 〃 | 전체 | 시드 17행 |
| 26 | `dashboard` | INS | 〃 | 전체 | |
| 27 | `widget` | INS | 〃 | 전체 | |
| 28 | `doc_chunk` | KNW | 〃 | `id`,`created_at` | `vector(1024)` + 생성 컬럼 |
| 29 | `structuring_draft` | KNW | 〃 | 전체 | 업로드 1:1 |
| 30 | `conversation` | KNW | 〃 | 전체 | |
| 31 | `message` | KNW | 〃 | 전체 | |
| 32 | `message_source` | KNW | 〃 | `id`,`created_at` | |

제약 실측: PK 32 · FK 59 · UNIQUE(테이블 제약) 21 · CHECK 78 · 인덱스 총 107개.

DDL 내 테이블 정의 순서는 FK 참조 순서를 따른다: IAM → `project` → INT → `work_product` → 나머지 STD → INS → KNW. `work_product` 가 `requirement`·`code_change`·`correction_action`·`meeting_record`·`acceptance_record` 보다 앞에 온다.

---

## 3. 타입 매핑 (논리 → 물리)

| 논리 타입 | PostgreSQL | 선택 근거 |
| --- | --- | --- |
| `ID` | `uuid` default `gen_random_uuid()` | pgcrypto 제공. 숫자 시퀀스를 쓰지 않으므로 도구 연동 데이터와 내부 데이터가 같은 키 공간을 쓴다 |
| `CODE` | `varchar(64)` | `REQ-001`, `CR-001`, 카탈로그 키 |
| `NAME` | `varchar(200)` | 조직명·프로젝트명·표시명 |
| `TITLE` | `varchar(500)` | 도구 제목 상한(대체로 255)의 2배 여유 |
| `TEXT` | `text` | PostgreSQL 에서 `varchar(n)` 대비 저장·성능 차이 없음 |
| `ENUM` | `varchar(40)` + `CHECK` | §1 |
| `BOOL` | `boolean` | |
| `INT` | `integer` | |
| `PCT` | `numeric(5,2)` | 0.00~100.00. 진척률 비교에 부동소수 오차를 넣지 않는다 |
| `DATE` | `date` | |
| `TS` | `timestamptz` | 전 테이블 UTC 저장. `timestamp`(무시간대)를 쓰지 않는다 |
| `JSON` | `jsonb` | 인덱싱·연산자 지원. `json` 은 텍스트 재파싱이라 쓰지 않는다 |
| `ID[]` | `uuid[]` | `conversation.project_scope` |
| `KEY[]` | `text[]` | `= ANY(...)` 포함 검사만 하므로 jsonb 불필요 |
| `VECTOR` | `vector(1024)` | pgvector 0.8.0. `bge-m3` 실측 차원과 일치 |
| `TSV` | `tsvector` **generated always ... stored** | |
| `URL` | `text` | 외부 URL 길이를 신뢰하지 않는다 |
| `HASH` | `char(64)` | SHA-256 hex 고정 64자. 가변 길이 오버헤드 제거 |
| 파일 크기 | `bigint` | `size_bytes` (100MB 상한은 CHECK) |

`password_hash` 는 `varchar(72)` — BCrypt 출력 60자 + `$2b$` 계열 변형 여유. 72는 BCrypt 입력 바이트 상한과 우연히 같은 값일 뿐 의미상 연관은 없다.

---

## 4. 인덱스 설계 근거

### 4.1 조회 패턴 → 인덱스 대응

| # | 조회 패턴 | 인덱스 | 근거 |
| --- | --- | --- | --- |
| 1 | `ProjectScope` 산출: "이 계정이 활성 할당된 프로젝트" | `ix_project_assignment__user_status (user_id, status)` | **모든 요청의 첫 쿼리**(INV-02). 선두 컬럼이 `user_id` 라 계정당 수 행으로 즉시 좁혀진다 |
| 2 | CLIENT 프로젝트 목록 | `ix_project__client_org_status (client_org_id, status)` | INV-03. 상태 탭 필터가 목록 화면 기본 |
| 3 | 로그인 | `uq_app_user__email` on `lower(email)` | 대소문자 무시 유일성과 조회를 **한 인덱스**로 처리. 애플리케이션의 `lower()` 정규화와 인덱스 표현식이 일치해야 인덱스를 탄다 |
| 4 | 프로젝트별 표준 데이터 조회 | `ix_requirement__project_status`, `ix_issue__project_status`, `ix_work_product__project_status`, `ix_risk__project_status_severity`, `ix_change_request__project_status`, `ix_correction_action__project_status_due` | `project_id` 를 **항상 선두**에 둔다. 권한 필터가 `project_id = ANY(?)` 로 무조건 붙기 때문에(INV-04) 선두가 아니면 어떤 쿼리도 인덱스를 못 탄다 |
| 5 | 연동 upsert | 6개 테이블의 `uq_*__source (tool_connection_id, external_id) where 둘 다 not null` | `INSERT ... ON CONFLICT` 의 **conflict target 자체**. 부분 인덱스라 문서·수기 유래 행(두 컬럼 null)이 인덱스에 들어가지 않는다 |
| 6 | 폴링 스케줄러 | `ix_tool_connection__poll (status, last_synced_at)` | "ACTIVE 이면서 가장 오래 동기화 안 된 연결" 을 선두 등치 + 후행 정렬로 한 번에 |
| 7 | 동기화 현황 화면 | `ix_sync_job__connection_started (tool_connection_id, started_at desc)` | 연결별 최근 잡 N건. `desc` 를 인덱스에 새겨 정렬 제거 |
| 8 | 잡 90일 보관 배치 | `ix_sync_job__retention (status, finished_at)` | 210만 행 예상 테이블의 삭제 대상 스캔. 이 인덱스가 없으면 일 1회 풀스캔 |
| 9 | 원본 변경 판정 | `ix_raw_artifact__hash (tool_connection_id, content_hash)` | `content_hash` 동일 → 승격·색인 스킵 |
| 10 | 잡 삭제 시 원본 FK | `ix_raw_artifact__sync_job` | `sync_job` 90일 삭제가 `ON DELETE SET NULL` 을 유발한다. 자식 인덱스가 없으면 삭제 1건마다 `raw_artifact`(20만 행) 풀스캔 |
| 11 | 추적표 역방향 전개 | `ix_trace_link__to (to_type, to_id, link_kind)` | `uq_trace_link__edge` 는 from 선두라 to 방향을 못 탄다 |
| 12 | 감사 조회 | `ix_entity_history__entity (entity_type, entity_id, changed_at desc)`, `ix_entity_history__project (project_id, changed_at desc)` | ADR-011 의 두 조회 패턴 각각 |
| 13 | 개발 활동량 measure | `ix_code_change__project_kind_time (project_id, kind, occurred_at desc)` | 15만 행. `row_filter` 의 `kind in (...)` + 기간 dimension 을 한 인덱스로 |
| 14 | 대시보드 위젯 로드 | `ix_widget__dashboard (dashboard_id) where status='ACTIVE'` | `DELETED` 위젯이 인덱스에 없다 |
| 15 | Q&A 사이드바 | `ix_conversation__user (user_id, pinned desc, last_message_at desc) where status='ACTIVE'` | 정렬 키 3개를 그대로 인덱스에 새겨 정렬 제거 |
| 16 | 화면 목록 부분일치 | `ix_requirement__title_trgm`, `ix_issue__title_trgm`, `ix_work_product__title_trgm` (GIN `gin_trgm_ops`) | 한국어 `LIKE '%키워드%'` 는 btree 로 불가. 검색용이 아니라 목록 필터용(§5) |
| 17 | 청크 검색 | §5 별도 절 | |

### 4.2 부분 유니크 인덱스 8종 — 테이블 제약이 아니라 인덱스인 이유

`WHERE` 절이 붙는 유니크는 PostgreSQL 에서 `CONSTRAINT` 문법으로 표현할 수 없다. 따라서 아래 8종은 `create unique index ... where ...` 로 만든다.

| 인덱스 | 조건 | 목적 |
| --- | --- | --- |
| `uq_project_assignment__active` | `where status='ACTIVE'` | 해제 후 재할당이 가능해야 하므로 `REVOKED` 행은 유일성 대상 밖 |
| `uq_sync_job__running` | `where status='RUNNING'` | INV-22. 종료된 잡은 무제한 |
| `uq_work_product__current` | `where is_current` | INV-12. 과거 버전 행은 제외 |
| `uq_acceptance_record__issued` | `where status='ISSUED'` | INV-17. 무효화(`VOIDED`) 후 재발행 허용 |
| `uq_dashboard__default` | `where is_default and status='ACTIVE'` | 프로젝트당 기본 대시보드 1개 |
| `uq_dashboard__name` | `where status='ACTIVE'` + `coalesce(project_id, '000…0'::uuid)` 표현식 | `project_id` 가 `null`(통합 대시보드)이면 SQL 유일성 규칙상 중복이 허용돼 버린다. 센티넬 UUID 로 치환해 `null` 끼리도 충돌시킨다 |
| `uq_requirement__code` | `where code is not null` | 도구 유래 요구사항은 `code` 가 없다 |
| `uq_*__source` × 6 | `where tool_connection_id is not null and external_id is not null` | §4.1 #5 |

`uq_app_user__email` 도 표현식(`lower(email)`) 때문에 인덱스로 만든다.

### 4.3 만들지 않은 인덱스와 근거

| 후보 | 미채택 근거 |
| --- | --- |
| `raw_artifact.payload_jsonb` GIN | 조회 경로가 `(tool_connection_id, external_id)` 하나뿐이다(논리 §5.7). jsonb 내부를 조건으로 찾는 쿼리가 없다 |
| `widget.spec_json` GIN | 위젯은 항상 `dashboard_id` 로 통째 로드한다. "이 measure 를 쓰는 위젯 찾기" 는 요건에 없다 |
| `code_change` 색인용 GIN/trgm | 커밋 15만 건을 검색 대상에서 제외했다(논리 §6.2). 인덱스를 만들 이유가 없다 |
| `entity_history.actor` | 조회 패턴이 "이 개체가 언제 바뀌었나" 뿐. "이 사람이 뭘 바꿨나" 는 요건에 없다 |
| `covering index` (`INCLUDE`) 일체 | 현재 규모(최대 210만 행, 대부분 6만 행 이하)에서 heap fetch 제거의 이득이 인덱스 크기·쓰기 비용을 넘지 않는다. 실측 느린 쿼리가 나오면 그때 추가한다 |
| 트리거 기반 `updated_at` 자동 갱신 | 논리 §0.3 이 JPA `@PreUpdate` 로 확정. 트리거를 두면 갱신 지점이 둘이 된다 |

---

## 5. 전문검색 · 부분일치 (한국어)

### 5.1 `content_tsv` 생성 컬럼

```sql
content_tsv tsvector generated always as
  (to_tsvector('simple', coalesce(source_title, '') || ' ' || content)) stored
```

| 결정 | 내용 | 근거 |
| --- | --- | --- |
| FTS config | **`'simple'`** | PostgreSQL 기본 설치에 한국어 형태소 사전이 없다. `korean` config 를 가정하면 배포 환경에서 `text search configuration "korean" does not exist` 로 기동이 깨진다. `simple` 은 공백·구두점 토크나이즈 + 소문자화만 하며 영문 키워드·이슈 키(`REQ-001`)·숫자에 정확히 동작한다 |
| 생성 컬럼 | `generated always ... stored` | 트리거 없이 DB 가 일관성을 보장한다. `to_tsvector(regconfig, text)` 는 IMMUTABLE 이라 생성 컬럼 식으로 적법하다(§7 검증 1에서 실증) |
| `source_title` 포함 | `coalesce(source_title,'') \|\| ' ' \|\| content` | 제목이 본문에 없어도 제목 매칭이 되게 한다 |
| 인덱스 | `ix_doc_chunk__tsv` GIN | |

### 5.2 pg_trgm 보완

`simple` 은 한국어 조사(`관제화면은`, `관제화면이`)를 서로 다른 토큰으로 만든다. 이 구멍을 trigram 이 메운다.

| 항목 | 내용 |
| --- | --- |
| 인덱스 | `ix_doc_chunk__content_trgm` GIN (`content gin_trgm_ops`) |
| 연산자 | `content % :q` (유사도 임계 초과) |
| **필수 세션 파라미터** | **`SET LOCAL pg_trgm.similarity_threshold = 0.1`** |

**임계값을 반드시 세션에서 설정해야 하는 이유(실측)**: `%` 연산자는 `pg_trgm.similarity_threshold` GUC 를 참조하며 기본값이 **0.3** 이다. 논리 설계 §6.3 이 정한 값은 0.1 이다. 기본값 그대로 두면 짧은 질의가 긴 청크와 매칭되지 않는다 — 검증 중 실측으로 확인했다.

```
기본(0.3): select count(*) from doc_chunk where content % '관제 화면'  →  0
0.1 설정 : 동일 쿼리                                                   →  1
```

`HybridSearchRepository` 는 어휘 검색 쿼리를 실행하는 트랜잭션에서 `hnsw.ef_search`·`hnsw.iterative_scan` 과 함께 이 파라미터도 `SET LOCAL` 로 설정한다. 셋 다 `SET LOCAL` 이므로 **반드시 트랜잭션 안에서 실행해야 한다** — 트랜잭션 밖에서는 `WARNING: SET LOCAL can only be used in transaction blocks` 와 함께 무시된다(실측 확인).

보조 trgm 인덱스 3개(`requirement.title`, `issue.title`, `work_product.title`)는 RAG 검색이 아니라 **화면 목록의 제목 부분일치 필터** 전용이다.

---

## 6. pgvector — HNSW 파라미터 근거와 재색인 절차

### 6.1 컬럼·인덱스 확정값

```sql
embedding vector(1024) not null
create index ix_doc_chunk__embedding_hnsw
  on doc_chunk using hnsw (embedding vector_cosine_ops) with (m = 16, ef_construction = 64);
```

| 파라미터 | 값 | 근거 |
| --- | --- | --- |
| 차원 | `1024` | `bge-m3` 실측 차원. 변환 로직을 두지 않는다(INV-29). 다른 차원은 **insert 자체가 실패**한다 — §7 검증 3에서 실증 |
| 인덱스 타입 | **HNSW** (IVFFlat 아님) | IVFFlat 은 리스트 중심점을 만들기 위해 **적재된 데이터가 필요**하다. 빈 테이블에 만들면 품질이 무너지고, 데이터 증가에 따라 주기적 재구축이 필수다. HNSW 는 빈 테이블에서 만들어도 증분 insert 로 그래프가 유지된다. 초기 배포 시점에 청크가 0건이라는 사실이 결정적이다 |
| 거리 연산자 클래스 | `vector_cosine_ops` (`<=>`) | `bge-m3` 임베딩을 정규화 없이 그대로 저장하므로 L2 가 아니라 코사인이 맞다. 유사도는 `1 - (embedding <=> :qvec)` |
| `m = 16` | pgvector 기본값 | 노드당 연결 수. 1년차 18만 행 규모에서 기본값이 재현율·인덱스 크기의 표준 균형점이다. 올리면 재현율이 오르지만 인덱스 크기와 빌드 시간이 선형 증가한다 |
| `ef_construction = 64` | pgvector 기본값 | 빌드 시 후보 큐 크기. 18만 행 × 1024차원에서 빌드 시간이 수 분 안에 끝난다. `m` 의 2배 이상이어야 하며 64는 이 조건을 만족한다 |
| `hnsw.ef_search = 100` | 세션 설정(기본 40) | top-40 을 요구하는데 기본 40 은 `ef_search >= limit` 를 겨우 만족해 재현율이 떨어진다. 2.5배 여유를 준다 |
| `hnsw.iterative_scan = relaxed_order` | 세션 설정(기본 off) | `project_id = ANY(?)` 권한 필터가 **항상** 붙는다. 필터 선택도가 낮으면(프로젝트 1개 = 전체의 1/20) 기본 모드에서는 `ef_search` 안에서 걸러져 결과가 40건에 못 미친다. `relaxed_order` 는 부족분을 반복 스캔으로 채운다. `strict_order` 가 아닌 이유는 RRF 융합이 어차피 순위를 재계산하므로 엄격한 거리 순서가 불필요하기 때문이다 |

세 GUC 는 전부 `SET LOCAL` 이므로 검색 트랜잭션 안에서 설정한다(§5.2 참조).

### 6.2 인덱스 사용 실증

1행·501행에서는 옵티마이저가 seq scan 을 고른다(정상 — 테이블이 작으면 그게 빠르다). 인덱스 자체의 사용 가능성은 `enable_seqscan = off` 로 강제해 확인했다.

```
Limit (actual rows=40 loops=1)
  ->  Index Scan using ix_doc_chunk__embedding_hnsw on doc_chunk (actual rows=40 loops=1)
        Order By: (embedding <=> '[0.1,...]'::vector)
```

**주의(구현자용)**: 질의 벡터가 `(select ...)` 서브쿼리로 들어가면 InitPlan 파라미터가 되어 **HNSW 인덱스를 타지 못한다**(실측: seq scan). `HybridSearchRepository` 는 반드시 벡터를 **바인딩 파라미터 또는 리터럴**로 넘긴다.

### 6.3 재색인 절차

**단위**: `(source_type, source_id)`. 부분 갱신하지 않는다.

```sql
begin;
delete from doc_chunk where source_type = :t and source_id = :id;
insert into doc_chunk (project_id, source_type, source_id, chunk_index, content, embedding,
                       source_title, source_uri, content_hash, meta_json)
values ...;
commit;
```

`ix_doc_chunk__source_lookup (source_type, source_id)` 가 삭제 경로를 받친다. `message_source.doc_chunk_id` 는 `ON DELETE SET NULL` 이라 과거 답변의 출처 카드가 스냅샷(`source_title`·`snippet`·`external_url`)으로 살아남는다.

### 6.4 대량 백필 시 인덱스 재구축 절차

18만 행을 한 번에 적재할 때는 HNSW 그래프에 행 단위로 삽입하는 것보다 전량 적재 후 한 번에 빌드하는 편이 빠르다. **운영 절차이며 마이그레이션에는 넣지 않는다.**

```sql
-- 1) 인덱스 제거 (검색 서비스 중단 구간)
drop index ix_doc_chunk__embedding_hnsw;

-- 2) 대량 적재
--    (애플리케이션 백필 잡 실행)

-- 3) 빌드 메모리를 올려 재생성 — CONCURRENTLY 는 테이블 락 없이 진행
set maintenance_work_mem = '2GB';
set max_parallel_maintenance_workers = 4;
create index concurrently ix_doc_chunk__embedding_hnsw
  on doc_chunk using hnsw (embedding vector_cosine_ops) with (m = 16, ef_construction = 64);

-- 4) 실패 시 INVALID 인덱스가 남는다. 반드시 확인 후 재시도
select indexrelid::regclass from pg_index where not indisvalid;
```

`maintenance_work_mem` 이 그래프 전체를 담지 못하면 pgvector 가 디스크 기반 빌드로 전환하며 수 배 느려진다. 빌드 전 `NOTICE: hnsw graph no longer fits into maintenance_work_mem` 경고가 나오면 값을 올려 다시 만든다.

### 6.5 차원 변경 시 (임베딩 모델 교체)

`vector(1024)` → 다른 차원은 `alter table ... alter column ... type vector(N)` 로 **기존 데이터가 있으면 실패**한다. 절차는 다음 하나뿐이다.

1. `truncate doc_chunk;` (청크는 파생 데이터라 원천에서 전량 재생성 가능)
2. `alter table doc_chunk alter column embedding type vector(N);`
3. `update doc_chunk set embedding_model = :new;` (빈 테이블이므로 무의미 — 신규 insert 기본값을 바꾼다)
4. 전량 재색인.

`embedding_model` 컬럼이 존재하는 이유가 이 절차의 추적성이다. 기동 시 `EmbeddingDimensionVerifier` 가 `information_schema` 의 `vector` typmod 와 `EmbeddingPort.dimension()` 을 대조해 불일치면 기동을 실패시킨다.

---

## 7. 파티셔닝 · 보존 정책

### 7.1 파티셔닝 — **전 테이블 미적용**

| 테이블 | 1년차 예상 행수 | 판단 |
| --- | --- | --- |
| `sync_job` | 210만 → 90일 보관 시 **52만** | 미적용 |
| `entity_history` | 40만 | 미적용 |
| `raw_artifact` | 20만 | 미적용 |
| `doc_chunk` | 18만 | 미적용 |
| `message_source` | 20만 | 미적용 |
| 나머지 27개 | 6만 이하 | 미적용 |

**근거**

1. 최대 테이블이 보관 정책 적용 후 52만 행이다. PostgreSQL 에서 파티셔닝이 이득을 내기 시작하는 지점은 통상 수천만 행 또는 개별 파티션 단위 `DROP` 으로 대량 삭제를 대체할 때다. 52만 행은 인덱스 하나로 충분하다.
2. 파티셔닝은 **유니크 제약에 파티션 키를 강제로 포함시킨다.** `uq_sync_job__running (tool_connection_id) where status='RUNNING'` 을 `finished_at` 범위 파티션 위에서 유지하려면 파티션 키를 유니크에 넣어야 하는데, 그러면 INV-22("연결당 RUNNING 최대 1건")가 파티션 단위로만 성립해 **불변식이 깨진다**. 같은 문제가 `doc_chunk` 의 `uq_doc_chunk__source` 에도 발생한다.
3. FK 대상 테이블을 파티셔닝하면 PG 14 에서 제약이 늘어난다(파티션 테이블을 참조하는 FK 지원은 PG 12+ 지만 운영 복잡도가 증가).

**재검토 조건**: `sync_job` 또는 `doc_chunk` 가 2,000만 행을 넘거나, 보관 배치의 `DELETE` 가 유지보수 창을 초과할 때. 그 시점에 `sync_job` 을 `finished_at` 월 단위 RANGE 파티션으로 전환하고 INV-22 는 `pg_try_advisory_lock` 단독 강제로 이관한다(이미 이중 방어 중).

### 7.2 보존 정책

| 대상 | 정책 | 실행 | 지원 인덱스 |
| --- | --- | --- | --- |
| `sync_job` | `status='SUCCEEDED' and finished_at < now() - interval '90 days'` 삭제. **`FAILED` 는 영구 보존** | 일 1회 배치 | `ix_sync_job__retention (status, finished_at)` |
| `refresh_token` | `expires_at < now() - interval '30 days'` 삭제 | 일 1회 배치 | `ix_refresh_token__user_expires` |
| `user_invitation` | `expires_at < now() - interval '30 days' and accepted_at is null` 삭제 | 일 1회 배치 | — (600행) |
| `raw_artifact` | **삭제하지 않는다** (INV-20 무손실 보존). 연결 삭제 시 CASCADE 로만 사라진다 | — | — |
| `entity_history` | **삭제하지 않는다** (감사 추적). `revoke update, delete` 로 애플리케이션 롤의 삭제 자체를 막는다 | — | — |
| `doc_chunk` | 원천 삭제·재색인 시에만 삭제. 시간 기반 보존 없음 | — | `ix_doc_chunk__source_lookup` |

`sync_job` 삭제는 `raw_artifact.sync_job_id` 의 `ON DELETE SET NULL` 을 유발한다. `ix_raw_artifact__sync_job` 이 없으면 이 배치가 20만 행 풀스캔을 반복하므로 해당 인덱스를 명시적으로 만들었다(§4.1 #10).

---

## 8. 스키마 초기화 전략 (멱등성)

DDL 은 `create table if not exists` 를 **쓰지 않는다.**

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 테이블 생성 | `create table` (조건 없음) | `if not exists` 는 "이미 있으면 조용히 넘어간다" 인데, **기존 테이블의 구조가 다르더라도 넘어간다.** 스키마 드리프트를 침묵으로 통과시키는 것은 마이그레이션 도구가 절대 해서는 안 될 일이다. Flyway 는 `flyway_schema_history` 로 적용 여부를 관리하므로 파일 자체의 멱등성이 필요 없다 |
| 확장 생성 | `create extension **if not exists**` | 확장은 스키마가 아니라 환경이다. 다른 DB 나 사전 프로비저닝으로 이미 설치돼 있을 수 있고, 그 경우 재실행이 정상이다. 설치 실패(권한 부족·미설치)는 여기서 즉시 기동 실패로 드러나야 한다(ADR-002) |
| 권한 회수 | `do $$ ... $$` 로 롤 존재 시에만 | 롤 프로비저닝은 인프라 책임. 롤이 없는 개발 환경에서 DDL 이 실패하면 안 된다 |
| 재실행 | **금지.** 재실행이 필요하면 DB 를 drop 하고 다시 만든다 | 개발 초기 단계이며 운영 데이터가 없다. V2 부터는 정방향 마이그레이션만 추가한다 |
| 롤백 | 스크립트를 만들지 않는다 | Flyway Community 에 undo 가 없다. 초기 스키마의 롤백은 `dropdb` 다 |
| 주석 | DDL 파일에는 섹션 구분 SQL 주석만. 설계 근거는 전부 이 문서 | 전역 규칙("코드에 주석을 쓰지 않는다") |

**로컬 초기화 절차**

```bash
dropdb --if-exists axlink && createdb axlink
psql -d axlink -v ON_ERROR_STOP=1 -f backend/src/main/resources/db/migration/V1__init.sql
```

Spring Boot 기동 시에는 Flyway 가 `classpath:db/migration` 을 읽어 자동 적용한다. `spring.jpa.hibernate.ddl-auto` 는 **`validate`** 로 고정한다 — `update` 는 Flyway 와 스키마 소유권을 다투게 된다.

---

## 9. DDL 검증 실행 로그

환경: PostgreSQL 14.18 (Homebrew) on aarch64-apple-darwin24.4.0 / pgvector 0.8.0 / pg_trgm 1.6 / pgcrypto 1.3.

### 9.1 검증 1 — DDL 무오류 실행

```
$ dropdb --if-exists axlink_ddlcheck
$ createdb axlink_ddlcheck
$ psql -d axlink_ddlcheck -v ON_ERROR_STOP=1 -q -f backend/src/main/resources/db/migration/V1__init.sql
DDL_EXIT=0
```

`ON_ERROR_STOP=1` 에서 종료 코드 0 = **단 한 건의 오류도 없음**. 수정 반복 없이 최초 실행에서 통과했다.

### 9.2 검증 2 — 스키마 실측

```
$ psql -d axlink_ddlcheck -At \
    -c "select 'tables='||count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'" \
    -c "select 'indexes='||count(*) from pg_indexes where schemaname='public'" \
    -c "select 'measures='||count(*) from semantic_measure" \
    -c "select 'dimensions='||count(*) from semantic_dimension" \
    -c "select 'filters='||count(*) from semantic_filter" \
    -c "select 'work_products='||count(*) from work_product"
tables=32
indexes=107
measures=13
dimensions=17
filters=17
work_products=22
```

| 항목 | 기대 | 실측 | 판정 |
| --- | --- | --- | --- |
| 테이블 수 | 32 (논리 §1) | 32 | ✅ |
| `semantic_measure` 시드 | 13 (논리 §7.2) | 13 | ✅ |
| `semantic_dimension` 시드 | 17 (논리 §9) | 17 | ✅ |
| `semantic_filter` 시드 | 17 (논리 §9) | 17 | ✅ |
| 데모 프로젝트 산출물 | 22 (INV-12) | 22 | ✅ |

제약 실측:

```
$ psql -d axlink_ddlcheck -c "select count(*) filter (where contype='f') fk, count(*) filter (where contype='c') ck,
                                     count(*) filter (where contype='u') uq, count(*) filter (where contype='p') pk
                                from pg_constraint where connamespace='public'::regnamespace"
 fk | ck | uq | pk
----+----+----+----
 59 | 78 | 21 | 32
```

확장·타입 실측:

```
 extname  | extversion       attname   | format_type
----------+------------    ------------+--------------
 pg_trgm  | 1.6             content_tsv | tsvector
 pgcrypto | 1.3             embedding   | vector(1024)
 plpgsql  | 1.0
 vector   | 0.8.0
```

`doc_chunk` 인덱스 6종 전량 생성 확인:

```
 ix_doc_chunk__content_trgm   | USING gin (content gin_trgm_ops)
 ix_doc_chunk__embedding_hnsw | USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')
 ix_doc_chunk__project        | USING btree (project_id)
 ix_doc_chunk__source_lookup  | USING btree (source_type, source_id)
 ix_doc_chunk__tsv            | USING gin (content_tsv)
 uq_doc_chunk__source         | UNIQUE btree (source_type, source_id, chunk_index)
```

### 9.3 검증 3 — 동작·제약 실증

임베딩 1024차원 insert, `<=>` 연산, 생성 컬럼, FTS, trgm 을 실제 데이터로 확인했다.

| 검사 | 결과 |
| --- | --- |
| `vector(1024)` insert | `INSERT 0 1` |
| `content_tsv` 자동 생성 | `'-001':12 '3초':7 'req':11 '갱신되어야':9 '관제':2 '발생':5 '요구사항정의서':…` |
| 코사인 자기유사도 `1-(v<=>v)` | `1.0000` |
| FTS `content_tsv @@ plainto_tsquery('simple','REQ-001')` | 1건 hit |
| trgm `content % '관제 화면'` (기본 임계 0.3) | **0건** → §5.2 의 세션 파라미터 필요성 확인 |
| trgm 동일 쿼리 (임계 0.1) | 1건 hit |
| HNSW 인덱스 사용 (`enable_seqscan=off`) | `Index Scan using ix_doc_chunk__embedding_hnsw … actual rows=40` |
| `hnsw.ef_search` / `hnsw.iterative_scan` GUC | 트랜잭션 내 `SET LOCAL` 로 `100` / `relaxed_order` 반영 확인 |

**제약 거부 실증 5건 — 전부 기대대로 실패했다.**

| 시도 | 결과 |
| --- | --- |
| 3차원 벡터 insert | `ERROR: expected 1024 dimensions, not 3` (INV-29) |
| `type='NOT_A_TYPE'` 산출물 insert | `ERROR: violates check constraint "ck_work_product__type"` (INV-11) |
| 동일 `(project, type)` 두 번째 `is_current` 행 | `ERROR: duplicate key … "uq_work_product__current"` (INV-12) |
| `start_date > end_date` 프로젝트 | `ERROR: violates check constraint "ck_project__period"` (INV-08) |
| `ADMIN@axlink.co.kr` (대문자) 계정 추가 | `ERROR: duplicate key … "uq_app_user__email"` — 대소문자 무시 유일성 동작 |

### 9.4 정리

```
$ dropdb axlink_ddlcheck
DROPPED
```

임시 데이터베이스는 검증 후 삭제했다. 로컬 PostgreSQL 에 잔여물이 없다.

---

## 10. 시드 데이터

### 10.1 카탈로그 시드

| 테이블 | 행수 | 원천 | 비고 |
| --- | --- | --- | --- |
| `semantic_measure` | 13 | 논리 §7.2 / §7.2.1 / §7.2.2 | `key`·`label`·`description`·`base_table`·`join_clause`·`row_filter`·`value_expr`·`value_type`·`unit`·`allowed_dimensions`·`allowed_filters`·`default_dimension` 전 컬럼 확정 |
| `semantic_dimension` | 17 | 논리 §7.3 | `description` 은 LLM 노출 문구로 본 문서에서 신규 작성(논리 설계에 값이 없던 유일한 컬럼) |
| `semantic_filter` | 17 | 논리 §7.4 | 〃 |

`period_month`·`period_week` 의 `select_expr` 와 기간 필터 3종의 `column_expr` 에는 **리터럴 문자열 `<TIME_COL>`** 이 저장되어 있다. `SemanticQueryBuilder` 가 measure 의 `base_table` 에 따라 논리 §7.3 하단 매핑표대로 치환한다. 치환 대상이 코드 상수이므로 사용자·LLM 입력이 이 자리에 들어올 경로는 없다(INV-26).

`allowed_dimensions`·`allowed_filters`·`enum_values` 는 `text[]` 리터럴(`'{a,b,c}'`)로 시드했다. 값에 쉼표·공백·한글이 없어 따옴표 없는 배열 리터럴이 안전하다.

### 10.2 조직·계정 시드

**공통 비밀번호: `Axlink!2026`** — BCrypt cost 10 해시로 저장했다. 세 계정 모두 같은 평문이며 salt 만 다르다.

| 역할 | 이메일 | 이름 | 조직 | 조직 유형 | 계정 UUID |
| --- | --- | --- | --- | --- | --- |
| `SUPER_ADMIN` | `admin@axlink.co.kr` | 플랫폼 관리자 | AX-Link 운영본부 | `CLIENT` | `b0000000-0000-4000-8000-000000000001` |
| `CLIENT` | `client@axlink.co.kr` | 발주사 담당자 | 한국디지털공사 | `CLIENT` | `b0000000-0000-4000-8000-000000000002` |
| `CONTRACTOR` | `contractor@axlink.co.kr` | 용역사 PM | 넥스트소프트 | `CONTRACTOR` | `b0000000-0000-4000-8000-000000000003` |

| 조직 | UUID | 유형 | 사업자번호 |
| --- | --- | --- | --- |
| AX-Link 운영본부 | `a0000000-0000-4000-8000-000000000001` | `CLIENT` | — |
| 한국디지털공사 | `a0000000-0000-4000-8000-000000000002` | `CLIENT` | `123-45-67890` |
| 넥스트소프트 | `a0000000-0000-4000-8000-000000000003` | `CONTRACTOR` | `210-81-11223` |

DDL 에 들어간 해시 값:

```
admin      $2y$10$iZc2Ri.WsQgbD20M68B/EuJqlTHhL1tvURkptR4oAJZvJkvdkSlUG
client     $2y$10$SvQwVA9vG4ToeaUdZsr2VOe8tIyxG0NmHp/BMgqkuBe6cnDj6svRy
contractor $2y$10$CBuzzYfNRwjTyDAPTsZd4O99aNvHxsWgADRA8ws2wvzkYpYCBneT2
```

`$2y$` 접두사는 Spring Security `BCryptPasswordEncoder` 가 `\A\$2(a|y|b)?\$` 패턴으로 정상 수용한다. 인코딩은 항상 `$2a$` 로 생성되지만 검증은 세 변형 모두 지원한다.

**해시 재생성 방법** (비밀번호 교체 시):

```bash
htpasswd -bnBC 10 "" '새비밀번호' | tr -d ':\n'
```

**보안 주의**: 이 세 계정은 **로컬 개발·데모 전용**이다. 운영 배포 전에 반드시 비밀번호를 교체하거나 계정을 삭제한다. 시드 계정 삭제는 `app_user.status = 'DISABLED'` 로 비활성화하는 편이 안전하다 — `project_assignment.assigned_by_user_id` 가 `ON DELETE RESTRICT` 라 물리 삭제가 막힌다.

### 10.3 데모 프로젝트 시드

| 항목 | 값 |
| --- | --- |
| UUID | `c0000000-0000-4000-8000-000000000001` |
| 프로젝트명 | 차세대 통합관제 시스템 구축 |
| 발주사 | 한국디지털공사 |
| 기간 | 2026-03-02 ~ 2026-12-31 |
| 상태 / SI 단계 | `ACTIVE` / `SI_2` |
| 산출물 | **22행** (`status='NONE'`, `applicable=true`, `is_current=true`) — INV-12 초기화 시연 |
| 할당 | 넥스트소프트 / 용역사 PM. 세부 권한 3종 모두 `true` |
| 대시보드 | `사업 현황` 1건 (`is_default=true`, 위젯 0개) |

22행의 `pm_activity`·`si_activity` 는 논리 §3.3 표를 그대로 시드했다. PRD §5.3 에서 두 활동이 함께 적힌 유형은 주 활동 하나만 넣었고(논리 §3.3 각주), `ck_work_product__activity`(둘 중 하나는 not null)를 전 행이 만족한다.

이 시드는 UC-03 "프로젝트 생성 트랜잭션에서 22행 bulk insert" 를 DB 레벨에서 미리 보여주는 예시다. 실제 프로젝트 생성은 애플리케이션이 동일한 22행을 삽입한다 — 시드 SQL 의 `values` 목록이 `ProjectCreationService` 의 초기화 테이블과 값이 일치해야 한다.

---

## 11. 후속 문서 인계 사항

| 항목 | 인계 대상 | 내용 |
| --- | --- | --- |
| 검색 트랜잭션 세션 파라미터 | `05-ai-pipeline` | `SET LOCAL hnsw.ef_search = 100`, `SET LOCAL hnsw.iterative_scan = relaxed_order`, **`SET LOCAL pg_trgm.similarity_threshold = 0.1`**. 셋 다 트랜잭션 필수 |
| 질의 벡터 바인딩 | `05-ai-pipeline` | 서브쿼리로 넘기면 HNSW 인덱스를 못 탄다. 파라미터 바인딩으로 넘긴다 |
| `<TIME_COL>` 치환 상수표 | `05-ai-pipeline` | 논리 §7.3 하단 `base_table` → 시간 컬럼 매핑 8행을 코드 상수 1개로 고정 |
| `ddl-auto=validate` | `06-backend` | Flyway 와 스키마 소유권 충돌 방지 |
| 보관 배치 3종 | `04-integration` | `sync_job` 90일, `refresh_token` 30일, `user_invitation` 30일 |
| `axlink_app` 롤 생성 | 인프라 | 롤 생성 후 `revoke update, delete on entity_history` 재실행 필요(V1 의 `do` 블록은 롤이 없으면 건너뛴다) |
| 시드 계정 처리 | 배포 | 운영 배포 전 비밀번호 교체 또는 `DISABLED` 전환 |
