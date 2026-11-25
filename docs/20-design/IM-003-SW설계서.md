# AX Link SW 설계서 (IM-003)

**2026년 AX 프로젝트 관리 운영 프레임워크 개발 용역**
발주 (재)전주정보문화산업진흥원 · 수행 유저인사이트(주)
**v0.1.5 초안** · 2026-11-25 · M3 시연 기준 (10-13 보강: 2.6 · 4.7 · 9.5 · 9.6 · 13.3 절, 12절 대응표 정리. 11-10: 5절 지표 목록에 위험 처리율. 11-16: 사용자 결정 DEC-05 로 9.1 역할·10절 인가, DEC-17 로 5.4 L3 대표값. 11-16 v0.1.3: 설계 문서 목록에 ARC-033 WBS 작업별 산출물·양식 지정. 11-16 v0.1.4: 5절 지표 목록에 요구사항 건수·산출물 건수(F-11, ARC-012 4-2절). 11-25 v0.1.5: 설계 문서 목록에 ARC-034 AI 판단 답변 방식)

> 설계 결정은 개별 설계 문서 `ARC-001`~`ARC-025` 에 결정 시점의 근거와 함께 남겨 왔다.
> 이 문서는 그 결정들을 한 체계로 묶어 "지금 시스템이 어떻게 생겼는가"를 한 번에 읽게
> 한 것이다. 개별 결정의 배경·대안·대가는 각 ARC 문서가 원본이고, 두 문서가 다르면 ARC 가 맞다.

---

## 0. 문서 개요

### 0.1 목적과 범위

요구사항정의서(IM-001)가 정한 소프트웨어 요구사항 41건을 어떤 구조로 구현했는지 적는다.
과업지시서 Ⅱ.5 나항이 정한 판정 기준은 기능 완성도가 아니라 **구조와 운영 개념의 시연
가능성**이므로, 이 문서도 화면 하나하나의 명세보다 데이터가 흐르는 구조와 그 구조를 지키는
규칙을 앞에 둔다.

범위는 저장소 `axlink` 의 백엔드(`app/`), 프런트엔드(`frontend/`), DB 스키마(`db/migration/`),
실행 구성(`infra/`)이다. 인수한 파일럿의 Java 백엔드는 ARC-001 로 저장소에서 제거했으므로
설계 대상이 아니다.

### 0.2 기준 문서

| 문서 | 역할 |
|---|---|
| 과업지시서 v1.1 | 요구의 원천. 모든 요구사항은 여기 조항에 근거한다 |
| IM-001 요구사항정의서 v0.4 | 요구사항 41건의 단일 정의처. 코드 체계 `SFR/SWFR/QUR/SER` |
| E2E 사용자 시나리오 | 발주기관·용역사 관리 순환의 흐름 |
| `docs/20-design/ARC-001`~`ARC-025` | 개별 설계 결정(부록 목록) |
| `docs/20-design/진척률-산정체계.md` | 진척률 계산 규칙과 데이터 수준 L1~L4 |
| `docs/20-design/인프라-배치방안.md` | 물리 배치와 폐쇄망 전환 계획 |
| `CLAUDE.md` | 작업 규약. 절대 규칙과 승계 제약의 원문 |

### 0.3 읽는 법

- 절마다 대응하는 요구사항 코드와 ARC 문서를 머리에 적었다.
- 테이블 이름 뒤의 `V##` 은 그 구조를 정한 Flyway 마이그레이션 번호다.
- "아직 없다", "표만 있다"는 그대로 적었다. 시연 범위 밖이거나 M4 이후 항목이다.

---

## 1. 설계 원칙

### 1.1 절대 규칙 세 가지

이 시스템의 신뢰성은 아래 세 규칙에서 나온다. 어떤 기능도 이 규칙을 우회하지 않는다.

| # | 규칙 | 지키는 구조 |
|---|---|---|
| 1 | **LLM 은 수치를 만들지 않는다.** 화면과 답변의 모든 숫자는 시맨틱 레이어가 SQL 로 집계한 값이다 | 시맨틱 레이어(5.6절), 수치 검문(7.5절), 산출 근거(5.7절) |
| 2 | **LLM 은 UI 를 만들지 않는다.** 인포 템플릿은 의도 해석 단계에서 *선택*될 뿐이다 | 인포 템플릿 카탈로그(8.1절), 위젯 = 데이터(8.2절) |
| 3 | **근거 없는 답은 막는다.** 유사도가 문턱 미만이면 답을 만들지 않고 근거 부족을 안내한다. 모든 답에 출처가 붙는다 | 근거 게이트(7.3절), 출처(7.6절) |

메뉴로 여는 화면과 자연어 질의는 **같은 데이터, 같은 템플릿**을 쓴다. 둘의 숫자가 다르면 버그다.

### 1.2 파일럿에서 승계한 제약

이전 제품(ax-pms)이 "프롬프트로 UI 를 고쳐도 화면이 변하지 않는" 문제로 중단된 기록에서 나온
제약이다(PRD 6.1.1).

| # | 제약 |
|---|---|
| 4 | 대시보드 레이아웃과 위젯 상태의 단일 원천은 서버 DB 다. 브라우저 저장소를 쓰지 않는다 |
| 5 | 위젯은 코드가 아니라 데이터(`spec_json`)다. 닫힌 유니온 타입을 두지 않는다 |
| 6 | 렌더 경로는 `spec → 렌더러` 한 단계다 |
| 7 | 프런트에 목업 데이터 파일을 두지 않는다. 화면 데이터는 전부 API 에서 온다 |
| 8 | 데이터 없는 메뉴를 만들지 않는다. 화면보다 테이블과 수집 경로가 먼저다 |
| 9 | 라벨은 발주기관 어휘로 쓴다. 도구 고유 용어는 화면에 내지 않는다 |

### 1.3 결정론이 먼저, 모델은 나중

수집·표준화·추적관계·진척률·산출물 판정은 규칙으로만 돈다. 모델이 개입하는 곳은 여섯
군데뿐이고(7.8절) 전부 "고르기" 아니면 "문장 만들기"다. 그래서 같은 입력에 같은 결과가 나오고,
모델을 바꿔도 숫자는 변하지 않는다.

### 1.4 자기참조

이 저장소 자체가 AX Link 의 1번 사업이다. 우리가 남기는 커밋·이슈·PR·산출물이 곧 수집
대상이자 시연 데이터이므로, 커밋 메시지의 추적 ID, 이슈의 `WBS: n.n` 라벨, `docs/` 의 산출물
경로가 설계의 일부다(2.5절 규약).

---

## 2. 시스템 구성

### 2.1 실행 구성

| 구성 요소 | 실행 | 포트 | 비고 |
|---|---|---|---|
| React + Vite 프런트 | Docker(개발: Vite 서버, 운영: Nginx 정적 제공) | 5173 (개발) · 8088 (운영 기본) | `/api/*` 를 백엔드로 넘긴다 |
| FastAPI 백엔드 | Docker, uvicorn worker 1개 | 8080 | 화면 API · 수집 잡 · 스케줄러가 한 프로세스. 그래서 컨테이너 하나만 띄운다 |
| PostgreSQL 16 + pgvector | Docker | 15432 (호스트) / 5432 (컨테이너) | 표준 모델 · 임베딩 · 대화 · 설정 전부 |
| Ollama | Docker | 11434 | 임베딩 `bge-m3`(1024차원). 생성 모델은 설정이 정한다 |
| Redmine + PostgreSQL | Docker | 3000 | 샘플 원천. 납품 대상이 아니다 |
| Flyway | Docker, 1회 실행 | - | `db/migration/V*.sql` 적용 |

개발은 `infra/docker-compose.yml`, 운영은 `infra/docker-compose.prod.yml`(미리 빌드한 이미지)로 띄운다.
기동 순서는 DB 준비 → Flyway 성공 → API 준비 → 웹이다. 시험 DB 는 별도 프로젝트(`infra/docker-compose.test.yml`)다.

외부를 부르는 곳은 원천 도구(GitHub · Redmine)와 Ollama 뿐이다. 개발 PC 에서는 Ollama 가
클라우드 모델(`gemma4:31b-cloud`)을 중계하지만, 납품 구성에서는 같은 자리에 온프레미스
모델이 들어가고 앱 코드는 바뀌지 않는다(ARC-011, 인프라-배치방안).

### 2.2 기술 스택

| 영역 | 선택 | 근거 |
|---|---|---|
| 백엔드 | Python 3.13 · FastAPI · uvicorn · Pydantic v2 · psycopg 3 | ARC-001. ORM 금지, SQL 직접 작성 |
| 스키마 | Flyway. `V1~V21` 승계, 이후 새 파일로만 | 기존 마이그레이션 수정 금지 |
| 벡터 | pgvector `vector(1024)` + HNSW, `tsvector`, `pg_trgm` | 하이브리드 검색이 네이티브 SQL 을 요구한다 |
| 문서 추출 | pdfplumber · python-docx · openpyxl · python-pptx · `hwp-hwpx-parser` | HWP 표 추출이 되는 Apache-2.0 파서 |
| 모델 호출 | Ollama REST. `LlmPort` · `EmbeddingPort` 뒤에 어댑터 하나 + Fake | 교체 시 상위 계층 무변경(SWFR.RAG.002) |
| 프런트 | React 19 · Vite · TypeScript · recharts · react-grid-layout · Tailwind | 파일럿 승계 |
| 시험 | pytest(DB 는 `*_test` 만 허용) · vitest · ruff · eslint · tsc | CI 는 ruff · pytest · 추적표 생성 검사를 돌린다 |

### 2.3 계층과 디렉토리

계층은 디렉토리와 1:1 로 대응한다. 데이터는 아래에서 위로 흐른다.

| 계층 | 디렉토리 | 책임 |
|---|---|---|
| 기반 | `app/auth` `app/org` `app/project` `app/common` | 로그인·토큰·초대, 조직·사용자, 사업·할당·수집 설정, 암호화·오류 기록 |
| [2] 연계 | `app/integration` | `port.ToolConnector` + `adapter/{github,redmine}_connector`, 수집 잡, 증분 |
| [3] 표준화·집계 | `app/standard` `app/dashboard` `app/review` `app/activity` | 승격, 추적관계, WBS 항목, 산출물 판정, 스냅샷, 확인 요청, 활동 기록 |
| [4] AI 실행 | `app/ai` `app/rag` `app/document` | 포트·어댑터, 청킹·임베딩·검색·근거 게이트·생성, 문서 추출·정형화 |
| [5] 인포 템플릿 | `app/dashboard/widget_template.py` `app/semantic` | 템플릿 23종 계약, 카탈로그로 SQL 조립 |
| [6] 워크스페이스 | `frontend/src` | 발주기관·용역사 화면 + AI 질의 |
| 스케줄 | `app/scheduler.py` | 서버 안 백그라운드 작업. 주기 수집·일별 스냅샷 |
| 스키마 | `db/migration` | V1~V44 |
| 산출물 | `docs/` | 납품 산출물이자 RAG 코퍼스 |

### 2.4 요청 처리 경로

**화면 요청.** 브라우저 → Vite 프록시 → FastAPI 라우터 → 인증(`auth/deps.py`, JWT) → 서비스
→ 저장소(SQL) → PostgreSQL. 라우터는 요청을 받아 서비스를 부를 뿐이고 값은 전부 SQL 이
만든다. 화면은 원천 도구를 직접 부르지 않는다. 마지막 수집 시점만큼 늦은 것이 설계다.

**수집 요청.** 동기화 실행 → 잡 번호를 먼저 돌려주고(202) → 어댑터가 원천을 읽기 전용으로
읽는다 → 원본을 `raw_artifact` 에 보존 → 규칙으로 표준 엔터티에 승격 → 추적관계 생성 →
산출물 판정 → 문장이 있는 것만 임베딩해 `doc_chunk` 로. 한 파이썬 프로세스가 화면 요청과
수집 잡을 다 처리하며 별도 워커는 없다.

### 2.5 저장소 규약 (자기참조의 일부)

| 규약 | 설계상 이유 |
|---|---|
| 커밋 `type(scope): 제목  [SWFR.CON.004]` | 추적관계 근거 `TEXT_REQ_CODE` 의 원천 |
| 이슈 참조는 `GH-n` · `RM-n`. 맨 `#n` 금지 | 도구가 둘이라 구분이 안 되고 Redmine 이 자기 이슈로 오해한다 |
| 이슈에 `WBS: n.n` 라벨 | 이슈를 WBS 항목에 딸리게 하는 유일한 근거(ARC-016) |
| WBS 는 `docs/00-management/WBS.xlsx` 커밋 파일 | GitHub 만 쓰는 업체도 L1 진척이 성립한다 |
| 산출물 문서는 `docs/` 경로에 | WBS 산출물 열과 저장소 경로로 대조된다 |

---

### 2.6 전 과정 시연 경로 (SWFR.DEM.001)

수집에서 질의까지 한 시스템 안에서 이어진다. 단계마다 앞 단계의 저장 결과만 읽는다.

| 단계 | 하는 일 | 모듈 | 남는 것 |
|---|---|---|---|
| 수집 | 원천 도구를 읽기 전용으로 읽는다(4.1 · 4.4) | `app/integration/sync.py` · `adapter/` | `raw_artifact`, `sync_job` |
| 표준화 | 원본을 표준 엔터티로 올리고 추적관계를 만든다(5.1 · 5.3) | `app/standard/service.py` · `trace_service.py` | `requirement` `issue` `code_change` `work_product` `trace_link` |
| 집계 | WBS 진척·산출물 판정·지표를 계산하고 일별로 떠 둔다(5.4~5.8) | `app/dashboard/` · `app/semantic/` | `wbs_item`, `progress_snapshot` |
| 화면 | 메뉴 화면과 대시보드가 같은 시맨틱 레이어 값을 보인다(8 · 9.2) | `frontend/src` | (읽기만) |
| 질의 | 같은 데이터·같은 템플릿으로 답하고 출처를 붙인다(7.1) | `app/rag/` | `conversation` `message` |

메뉴와 질의가 같은 함수를 쓰므로 숫자가 다르면 버그다(1.1절). 수동 동기화 한 번으로 이 다섯 단계가
한 흐름에 돈다(2.4절 수집 요청).

**아직 없는 것:** 이 경로를 처음부터 끝까지 시연한 기록(TST)이 없다. 시연 시나리오(WBS 6.4,
`docs/30-test/E2E-시연-시나리오.md`)와 함께 남긴다. 선행 기능 중 미구현이 있는 단계(일정 준수율 13.3절,
결함 지표)는 시연에서 "값 없음"으로 보인다.

## 3. 데이터 설계

### 3.1 세 층: 원본 → 표준 → 축

```
raw_artifact (원본 payload 그대로)
   └─ 규칙으로 승격 ─▶ 표준 엔터티 (requirement · issue · risk · code_change · work_product)
                          └─ 근거가 있을 때만 ─▶ trace_link
wbs_item (축) ◀─ 산출물 열로 판정 ─ work_product / document_upload
   └─ 라벨로만 ─▶ issue.wbs_item_id
progress_snapshot (하루 한 줄)
```

- **원본 보존**(SWFR.PIP.002). `raw_artifact` 는 `(연결, external_id)` 유일이고 내용 해시로 같은
  원본을 두 번 넣지 않는다. 표준화 규칙을 고치면 재수집 없이 재승격한다.
- **표준 엔터티**(SWFR.PIP.001, ARC-005). 도구가 달라도 같은 모양이며 `tool_connection_id`
  `external_id` `external_url` `source_kind`(TOOL | DOCUMENT | MANUAL) 을 공통으로 갖는다.
  화면과 지표는 여기만 읽는다.
- **축**(SWFR.PIP.010, ARC-016). `wbs_item` 이 진척·일정·산출물 판정·확인 요청의 기준이다.
- **관계**(QUR.PIP.001). `trace_link` 는 `evidence_kind not null` 제약이 있어 근거 없는 행이 들어갈 수 없다.

### 3.2 테이블 군

| 군 | 테이블 | 정한 마이그레이션 |
|---|---|---|
| 조직·사용자 | `organization` `app_user` `user_invitation` `refresh_token` | V1, V20(아이디 로그인) |
| 사업 | `project` `project_assignment` `project_invite` `project_schedule` | V1, V6~V10, V38~V40 |
| 연계 | `tool_connection` `sync_job` `raw_artifact` | V1, V11, V22 |
| 표준 엔터티 | `requirement` `issue` `risk` `code_change` `work_product` `entity_history` | V1, V13, V21 |
| 관리 객체(표만) | `change_request` `correction_action` `meeting_record` `acceptance_record` `progress_record` | V1, V8 |
| 축·관계 | `wbs_item` `trace_link` | V31, V32(판정 컬럼), V24(근거) |
| 집계 | `progress_snapshot` `semantic_measure` `semantic_dimension` `semantic_filter` | V23, V18, V19, V42~V44 |
| 대시보드 | `dashboard` `dashboard_preset` `widget` | V1, V15, V16, V18 |
| 문서 | `document_upload` `structuring_draft` `doc_chunk` | V1, V33~V35 |
| 질의 | `conversation` `message` `message_source` `route_cache` | V1, V3, V14, V28~V30 |
| 관리 순환 | `review_request` `review_request_event` `activity_event` `notification_seen` | V26, V37, V41 |
| 모델 설정 | `llm_setting` `llm_model_cache` | V27 |
| 운영 | `app_error_log` | V36 |

총 45개 테이블(Flyway 이력 제외). 파일럿에서 `V1~V21` 을 승계했고 이후는 새 파일로만 늘렸다.

### 3.3 산출물 항목과 29110

ISO/IEC 29110-5-1-2 Basic Profile 은 프로세스 인증이 아니라 **분류 참조 틀**로 읽는다
(ARC-005 2절). 29110 산출물 목록은 `work_product` 22종 유형으로 두고, 도구에서 흘러드는
레코드는 그 산출물의 증거가 되는 표준 엔터티로 뺐다. 09.21 이후 22종은 항목 목록이 아니라
**태그**다(ARC-016 3-3-1). 어떤 산출물을 내야 하는지는 사업마다 WBS 산출물 열이 정하고,
22종 점검표는 인도 점검용 보조 화면으로 남는다.

29110 의 활동 구분(사업관리 PM 4단계, 소프트웨어 구현 SI 6단계)은 유형마다 하나로 정해져
있다. 활동은 사람이 입력하는 값이 아니라 유형에서 나오는 속성이다. 정형화 확정 화면에서
고르지 않고, 수집이나 문서 확정이 새 버전을 만들 때도 유형 표에서 다시 읽는다(GH-184).
관리 축은 WBS·요구사항·산출물이고, 29110 은 그 산출물을 표준 분류에 대응시키는 참조로만
쓴다. 유형별 원본 표와 이 저장소의 대응물은 ARC-005 4절에 있다.

| 활동 | 단계 | 산출물 유형 |
|---|---|---|
| PM_1 | 계획 수립 | 과업지시서 · 사업수행계획서 · 사업 저장소 |
| PM_2 | 계획 실행 | 진척 보고 · 회의록 · 변경 요청서 · 저장소 백업 |
| PM_3 | 평가와 통제 | 시정조치 대장 · 검토 결과 |
| PM_4 | 종료 | 검수확인서 · 확인 결과 |
| SI_1 | 착수 | (해당 유형 없음) |
| SI_2 | 요구사항 분석 | 요구사항정의서 · 요구사항추적표 |
| SI_3 | 설계 | 설계서 · 시험계획서 |
| SI_4 | 구현 | 프로그램 구성요소 |
| SI_5 | 통합과 시험 | 통합 소프트웨어 · 시험결과서 · 운영지침서 · 사용자취급설명서 |
| SI_6 | 인도 | 소프트웨어 형상 · 유지보수문서 |

적용 범위: 22종 유형 정의, 사업 생성 때 만드는 산출물 목록, 시맨틱 차원 `iso_activity`.
쓰지 않는 것: 29110 프로세스 인증·준수 판정, 22종 전부를 필수 제출물로 강제하는 것.
SI_1 착수에 대응하는 유형은 22종에 없다. 착수보고는 WBS 1.1 산출물로 관리한다.

### 3.4 스키마 변경 규칙

- 스키마 변경은 반드시 새 `V##__` 파일이다. 기존 파일은 고치지 않는다.
- 새 값(템플릿·유형·도구)은 DB CHECK 제약에 있어야 한다. 시험이 CHECK · 프런트 렌더러 ·
  서버 카탈로그의 수를 같게 고정한다.
- 시험은 이름이 `_test` 로 끝나는 DB 에만 붙는다. 개발 DB 를 두 번 지운 뒤 만든 규칙이다.

---

## 4. 연계·수집 설계

*SWFR.CON.001~007 · QUR.CON.001 · ARC-003 · ARC-004*

### 4.1 포트와 어댑터

```
integration/sync.py  ──▶  port.ToolConnector  ──▶  adapter/github_connector.py
      (도구를 모른다)         verify · fetch_items · fetch_file       adapter/redmine_connector.py
```

새 도구의 비용은 어댑터 파일 하나 + 등록소 한 줄 + `tool_connection.tool` CHECK 한 줄이다.
Redmine 을 붙일 때 상위 계층 변경은 0줄이었다. 자격증명은 복호화한 문자열 하나로 넘기고
해석(헤더 이름 등)은 어댑터 책임이다.

| 도구 | 인증 | 수집 항목(`item_kind`) | 증분 |
|---|---|---|---|
| GitHub | PAT Bearer | 이슈 · PR · 커밋 · 마일스톤 · 파일(WBS) · 트리(경로 판정용) | `since=` |
| Redmine | `X-Redmine-API-Key` | 이슈(관계·저널 포함) · 버전 · 트래커 | `updated_on>=` |

### 4.2 매핑 설정 (SWFR.CON.002)

연결마다 `mapping_json` 에 판별 이름을 둔다. 요구사항 라벨, 리스크 트래커, `REQ ID` 커스텀 필드
이름, `requirement_from_issues`(기본 꺼짐) 등이다. 코드를 고치지 않고 화면에서 바꾼다.

### 4.3 증분과 재현 (SWFR.CON.005)

첫 회는 전체, 그다음부터 마지막 성공 수집의 시작 시각을 커서로 증분 수집한다. 겹쳐 읽되
내용 해시로 걸러 몇 번을 돌려도 같은 결과다. 변화가 없어도 승격은 다시 도는데 이는 유휴
비용으로 기록만 해 두었다.

### 4.4 읽기 전용 보장 (QUR.CON.001, ARC-004)

세 겹이다. ① `tests/test_readonly_guard.py` 가 어댑터 소스에 GET 외 HTTP 호출이 있으면 CI 를
실패시킨다. ② 자격증명은 읽기 권한만 부여한다. ③ 시연 전후 원천 도구 변경 이력이 비어 있음을
1회 확인한다.

### 4.5 서버 안 스케줄러 (SWFR.CON.005 · SWFR.PIP.005)

cron 에 맡기면 폐쇄망 반입 요소가 하나 늘어 앱이 뜰 때 백그라운드 작업 하나를 띄운다.
매 분 사업별 설정(`project_schedule`)을 보고 판단한다. 판단 함수는 순수 함수라 시계를 주입해
시험한다.

| 설정 | 선택지 | 뜻 |
|---|---|---|
| 수집 주기 | 수동 · 15분 · 30분 · 1시간 · 3시간 · 6시간 · 12시간 · 하루 한 번(기준 시각) | 활성 연결마다 증분 수집 |
| 스냅샷 | 24 · 12 · 6 · 3 · 1시간 + 기준 시각 | 사업 시간대(Asia/Seoul) 기준 |

기동 직후 오늘 스냅샷이 없으면 찍는다. 하루가 비면 추이가 끊기기 때문이다. 설정은
발주기관·플랫폼 관리자만 바꾸며 용역사에게는 보이지 않는다.

### 4.6 문서 수집 (SWFR.CON.007)

업로드는 접수만 하고, 추출 → 색인 → 초안은 API 안 작업자가 대기열에서 가져가 뒤에서 한다(ARC-021). PDF(표는 행·열 유지, bbox 오류 시 본문
추출로 대체) · DOCX · XLSX · PPTX · HWP · HWPX · MD · TXT. 같은 내용을 다시 올리면 새 행을 만들지
않고 재처리한다. 문서는 WBS 항목에 붙일 수 있고(`document_upload.wbs_item_id`) 29110 유형 태그를 가진다.

---

### 4.7 연결 등록과 연결 확인 (SWFR.CON.006)

발주기관이 사업 설정에서 도구를 붙인다. 등록과 확인을 나눈다.

| 단계 | API | 하는 일 |
|---|---|---|
| 저장 전 확인 | `POST /connections/test` | 입력한 주소·대상·토큰으로 어댑터 `verify` 를 부른다. 저장하지 않는다 |
| 등록 | `POST /projects/{id}/connections` | 토큰을 `common/crypto.py` 로 암호화해 저장하고 끝 네 자리 힌트만 남긴다. 상태 `DRAFT` |
| 저장 후 확인 | `POST /connections/{id}/test` | 저장된 토큰을 풀어 `verify`. 저장소에 닿으면 `VERIFIED` 와 확인 시각 |
| 운영 상태 | `PATCH /connections/{id}/status` | `VERIFIED`·`PAUSED` → `ACTIVE`, `ACTIVE` → `PAUSED` 만 허용 |
| 주소·토큰 변경 | `PATCH /connections/{id}` | 대상이나 토큰이 바뀌면 상태를 되돌려 다시 확인하게 한다 |

- `verify` 는 저장소에 닿는지와 항목(이슈·PR·커밋 등)별로 실제로 읽히는지를 따로 돌려준다(읽힘·거부 목록).
  토큰 권한이 빠진 항목은 붙이는 시점에 드러나고, 수집 때는 그 항목만 건너뛰며 잡에 남긴다.
- 주소는 https 만 받는다(로컬 루프백만 예외). 평문 토큰이 네트워크로 나가지 않게 하려는 것이다.
- 토큰은 화면·로그·확인 응답에 나오지 않는다(10절).
- 수집(`POST /connections/{id}/sync`)은 `VERIFIED` 이후 상태에서만 받는다.

## 5. 표준화·집계 설계

### 5.1 승격 (SWFR.PIP.002, ARC-005)

`standard/service.promote_connection` 이 `raw_artifact` 를 읽어 라벨·트래커·필드로 갈래를 정한다.
이슈는 언제나 `issue` 로 흐르고, 리스크 트래커는 `risk`, 커밋·PR 은 `code_change` 다. 이슈를
요구사항으로 올리는 경로(`tool_connection.requirement_from_issues`, V53)는 연결별 선택이며 새 연결은
꺼져 있다. V53 이전 연결은 켜진 채로 남았다가 요구사항 기준선을 확정할 때 꺼진다. 기준선을 확정한
사업은 설정과 상관없이 이슈로 요구사항을 만들지 않는다(ARC-016, ARC-028). 꺼진 연결의 요구사항
라벨 이슈는 일반 이슈로 가고, 이미 이어진 요구사항은 근거 상태만 갱신한다.

### 5.2 요구사항의 원천

요구사항의 정의처는 요구사항 명세서다. 용역사가 명세서를 기준선으로 등록해 추출 결과를 정리·제출하고
발주기관이 확정하면 `requirement` 에 `(project, code)` 유일로 들어간다(ARC-028). 확정 전 목록은
`requirement_baseline_item` 에만 있다. 문서 정형화 초안(6.2절)의 확정은 산출물 버전만 등록하고
요구사항을 만들지 않는다. 이슈·커밋·시험은 그 코드를 **참조**할 뿐이다. 사업에 없는 코드를 가리킨
근거는 잇지 않고 `requirement_unresolved_ref` 에 남겨 보인다.

### 5.3 추적관계 (SWFR.PIP.003 · PIP.004 · QUR.PIP.001, ARC-007)

원본에 사람이 남긴 명시적 근거에서만 만든다. 유사도로 잇지 않는다.

| 근거 유형 | 어디서 | 링크 |
|---|---|---|
| `TEXT_REQ_CODE` | 커밋 메시지·이슈 제목의 `SWFR.CON.004` | IMPLEMENTS · TESTS · DESIGNS |
| `TEXT_ISSUE_REF` | `GH-n` · `RM-n` | 이슈 ↔ 커밋 |
| `CUSTOM_FIELD` | Redmine `REQ ID` | 이슈 → 요구사항 |
| `ISSUE_RELATION` | Redmine 이슈 관계 | 이슈 ↔ 이슈 |
| `TEXT_FILE_PATH` | 산출물 경로 | DELIVERS |
| `DOC_REQ_REF` | 저장소 설계 문서의 명시적 참조(관련 행 · 대응표 · 절 제목) | 설계 문서 → 요구사항 DESIGNS (ARC-024) |
| `TEXT_WBS_ID` | `WBS: n.n` 라벨 | 이슈 → WBS 항목. **아직 없다**(ARC-016 7절 3단계) |

커밋·PR 은 변경 파일을 알면 파일로 관계를 정한다(코드 → 구현 관련 변경, 시험 파일 → 시험 연결,
설계 문서 → 설계, 관리 문서만 → 잇지 않음). 모르면 제목 유형으로 정한다(ARC-024 2-3). 구현 관련
변경은 구현 완료 증거가 아니고, 시험 연결은 시험 통과 증거가 아니다.

멱등 키는 `(from_type, from_id, to_type, to_id, link_kind)` 유니크다. 다시 확인되지 않은 자동 링크는
지우지 않는다. 원천 근거가 사라졌으면 `BROKEN`, 분류 정정으로 다른 링크에 대체됐거나 제외됐으면
`SUPERSEDED` 로 두고 사유·시각을 남긴다. 수동 링크는 덮지 않는다. 추적표 `docs/traceability.csv` 는
사람이 쓰지 않고 생성기가 만든다. 생성기도 같은 판별 함수로 설계 근거를 읽는다(ARC-024 4절).

### 5.4 WBS 축 (SWFR.PIP.006 · PIP.010, ARC-016, 진척률-산정체계)

`docs/00-management/WBS.xlsx` 를 파싱해 `wbs_item` 에 적재한다(재업로드 시 갱신, 빠진 번호는
비활성). 열은 WBS ID · 업무분류 · 산출물 · 시작일 · 종료일 · 가중치 · 계획 · 실적이다.

| 값 | 식 |
|---|---|
| 대표 진척률 | Σ(말단 가중치 × 실적) |
| 계획선(오늘) | Σ(말단 가중치 × clamp((오늘 − 시작) / (종료 − 시작), 0, 1)) |
| 편차 | 진척률 − 계획선 (%p, 음수면 지연) |
| 지연 작업 | 종료일 경과 · 실적 < 100%, 또는 계획선 대비 20%p 이상 뒤짐 |
| 격차 경고 | 실적 80% 이상인데 산출물 미제출 또는 열린 이슈 |

진척률은 이슈·산출물로 추정하지 않는다. WBS 가 없으면 L2~L4 규칙(진척률-산정체계)으로
내려가되 추정임을 표시하고, 근거가 없으면 산출하지 않는다. WBS 가 없는 사업(L3)의 대표값은
이슈 기반 추정 진척률이다. 대상 일반 이슈의 진척도를 같은 가중치로 평균하고 진척도가 없는
이슈는 0 으로 세며 그 건수를 밝힌다. 대상 이슈가 있는데 진척도가 모두 없으면 산출 불가다.
일반 이슈 해결률은 별도 지표다(DEC-17, 진척률-산정체계 4절). 스냅샷은 대표값의 산식을 함께
적어(`representative_basis`, V65) 2026-11-16 전 L3(해결률) 행과 섞지 않는다.

### 5.5 산출물 판정 (SWFR.PIP.009, ARC-016 3-3)

WBS 산출물 열은 자유 텍스트라 링크 표를 미리 만들 수 없다. 수집·업로드 뒤 판정을 돌려
`wbs_item` 에 상태와 근거를 적는다(V32).

| 순서 | 규칙 | 근거 |
|---|---|---|
| 0 | `LINKED_DOC` 항목에 직접 붙인 문서 | 문서 상세 링크 |
| 1 | `REPO_PATH` 저장소 경로(폴더 포함, GitHub 트리) | 저장소 URL |
| 2 | `FILE_NAME` 올린 파일 이름 | 문서 상세 링크 |
| 3 | `PRODUCT_TYPE` 29110 유형 태그 | 문서 상세 링크 |

맞는 것이 없으면 `MISSING`, 종료일까지 지났으면 `OVERDUE`. 판정 결과는 시맨틱 지표
`wbs_deliverable_*` 로 집계되고 산출물 화면은 이 목록을 보인다. 용역사는 그 화면에서 항목에
바로 올린다.

### 5.6 시맨틱 레이어 (SWFR.WEB.001 · PIP.005~009, ARC-006)

화면의 모든 수치는 카탈로그 조각으로 조립한 SQL 의 집계 결과에서만 나온다.

```
semantic_measure (지표 29종: base_table · value_expr · 분자·분모 · 목표 · 산출 근거)
semantic_dimension (차원: select_expr · label_expr · 시간 축 여부)
semantic_filter
        ▼ builder.validate → builder.build (2단계)
WidgetQuery {measure, dimensions ≤ 2, filters, projectScope, limit}  ──▶  SQL  ──▶  WidgetDataResponse
                                                                      d0 · d0_label · value · total · previousTotal · target · basis
```

카탈로그에 없는 키는 저장도 조회도 되지 않는다(`CATALOG_VALIDATION_FAILED`). 사업 범위는
호출자의 접근 권한과 교차한 뒤에만 적용된다(`PROJECT_ACCESS_DENIED`). 비율 지표는 분자·분모를
같은 SQL 에서 함께 세어 "0% (0건 / 41건)" 처럼 보인다.

### 5.7 산출 근거 (QUR.WEB.002, V42~V44)

지표마다 사람 말로 된 근거를 둔다. 무엇을 무엇으로 나누는지, 값이 언제 움직이는지,
올리려면·줄이려면 무엇을 해야 하는지. 위젯 설명과 AI 답변이 같은 문장을 보인다. "요구사항
이행률 0%" 가 왜 0 인지(시험 결과가 연결돼야 검증완료로 올라간다)를 모델이 아니라 이 문장이
말한다.

### 5.8 일별 스냅샷 (SWFR.PIP.005, V23)

사업·일자당 한 줄. 같은 날 두 번 찍으면 나중 값이 이긴다. 진척(대표·WBS 실적·계획선·지연 수),
이슈(전체·해결), 요구사항(전체·검증), 리스크(전체·종료), 산출물(전체·제출·승인)을 분자·분모로
보존해 비율은 조회 때 계산한다. 추이·보고·"지난 보고 이후 변화" 의 원천이며, 스냅샷 화면이
행과 전일 대비 증감을 그대로 보인다. 찍은 사실은 활동 기록(LOG)에 남는다.

### 5.9 지표 카탈로그 요약

| 축 | 지표 | 원천 |
|---|---|---|
| 진척 | `progress_representative_pct` `progress_wbs_pct` `progress_planned_pct` `progress_variance_pct` `progress_behind_task_count` | 스냅샷 |
| 일정 | `schedule_variance_pct` | 스냅샷 (V48, ARC-020) |
| 품질 | `requirement_fulfillment_rate` `requirement_count` `requirement_test_trace_rate` `issue_resolution_rate` `issue_count` `open_issue_count` `issue_avg_resolution_days` `issue_resolution_days_p50/p90` `open_risk_count` `risk_resolution_rate` `test_pass_rate` `correction_overdue_count` `change_request_count` | 표준 엔터티 |
| 산출물 | `work_product_approval_rate` `work_product_count` `work_product_missing_count` `wbs_deliverable_submitted_rate` `wbs_deliverable_missing_count` `wbs_deliverable_overdue_count` | `work_product` · `wbs_item` |
| 추이 | `snapshot_requirement_fulfillment_pct` `snapshot_risk_closed_pct` `snapshot_work_product_approval_pct` `progress_issue_pct` `progress_work_product_pct` | 스냅샷 |
| 활동 | `code_activity_count` | `code_change` |

일정 준수율(SWFR.PIP.007)은 마일스톤 원본만 보존된 상태다(3.2절 표만 있는 군과 같은 처지).
M4 에서 `milestone` 승격과 함께 지표를 추가한다.

---

## 6. 문서 처리 설계

### 6.1 추출과 색인 (SWFR.CON.007 · SWFR.RAG.003 · RAG.004)

추출기(`document/extractor.py`)가 포맷별로 텍스트와 표를 뽑고 원문 위치(페이지·시트·행·문단)를
붙인다. 청킹은 문장 경계를 지키며 라벨을 되붙이고, `bge-m3` 로 임베딩해 `doc_chunk` 에 넣는다.
수집한 이슈·요구사항·리스크도 문장이 있으면 같은 표에 색인된다(`source_type`). 문서 상세
화면 오른쪽이 추출 결과 원문이고, 왼쪽이 WBS 항목·유형 태그 등 설정이다.

### 6.2 정형화 초안 (ARC-009)

올린 문서에서 산출물 유형과 요구사항 목록의 초안을 뽑고, **사람이 확정한 뒤에만** 표준 모델에
넣는다. 표 규칙(머리행으로 열을 정하고 코드 꼴 행만) → 줄 규칙(표가 없을 때만) 순서이고,
모델은 규칙이 못 정한 유형 하나와 제목 한 줄만 답한다. 코드·본문·중요도·건수는 문서 글자에서만
온다. 상태는 PROPOSED → CONFIRMED | REJECTED | MANUAL_OVERRIDE 다.

---

## 7. 자연어 질의 설계

*SWFR.RAG.001~007 · QUR.RAG.001~002 · ARC-010 · ARC-013 · ARC-014 · ARC-015*

### 7.1 한 질문의 경로

```
질문 + 같은 대화의 최근 3턴
  ─▶ ① 판정 (LLM 호출 1, 캐시 먼저)   route · measure · dimensions · template · list · followUp
  ─▶ ② 재료 (모델 없이)              집계 값 + 산출 근거 · 목록 행 · 근거 청크 · 현황 그림
  ─▶ ③ 생성 (LLM 호출 2)             문장만. 값은 인용, 근거 없으면 모른다, [그림 N] 표식
  ─▶ ④ 서버 검문                     집계 값·근거·앞 답에 없는 숫자는 경고
  ─▶ ⑤ 출력                         본문 + 그림 + 출처 [1]…[n]
```

SSE 로 `start → delta… → sources → infographic… → done` 순으로 흘리고 트랜잭션은
prepare · stream · finish 셋이다. 답을 만든 뒤에만 판정을 캐시에 넣는다.

### 7.2 판정 (SWFR.RAG.005)

| 경로 | 언제 | 값의 원천 |
|---|---|---|
| `AGGREGATE` | 카탈로그 지표로 셀 수 있는 질문. 지표 이름을 부르면 값·이유·방법 어느 것을 묻든 그 지표 | 시맨틱 SQL |
| `DOCUMENT` | 문서·이슈·회의록 내용 | 근거 청크 |
| 목록 (`list`) | 이슈·요구사항·리스크·산출물 나열. 상태 조건 OPEN / CLOSED / ALL | 표준 모델 행 → `DATA_TABLE` |
| `MIXED` | 집계 + 문서 근거가 함께 | 둘 다 |
| `OVERVIEW` | 사업 전반. 문서를 못 찾은 질문의 내려갈 곳 | 현황 그림 최대 4장 |
| `OFF_TOPIC` | 사업과 무관 | 서버 고정 문장, 모델 안 부름 |

모델은 키만 고른다. 카탈로그에 없는 키면 문서 경로로 내려가고 억지로 맞추지 않는다.

### 7.3 근거 게이트 (SWFR.RAG.007)

하이브리드 검색(7.4절)의 최고 코사인 유사도가 문턱(`rag_min_similarity`, 기본 0.55) 미만이면
모델을 부르지 않고 근거 부족 문안을 저장한다. 표(목록)를 만들었으면 표준 모델 행이 근거이므로
막지 않는다. 무관하다고 판정했는데 근거가 실제로 있으면 근거가 판정을 이긴다.

문서 근거가 막힌 질문에 DB 현황이 있어도 원질문에는 답하지 않는다(ARC-017).
- 서버 문안과 함께 `참고 현황 · ` 제목의 그림만 붙이고, 출처·각주는 없다.
- `finishReason` 은 `NO_EVIDENCE` 다.
- DB 현황도 없으면 근거 부족 안내로 끝난다.

### 7.4 하이브리드 검색 (SWFR.RAG.004)

벡터(HNSW 코사인)와 어휘(`tsvector` + `pg_trgm`) 후보를 RRF(k=60)로 섞어 상위 후보를 고르고
코사인 내림차순으로 최종 5건을 쓴다. 검색어는 판정이 다듬은 핵심어(`rewritten`)다.

### 7.5 생성과 수치 검문 (SWFR.RAG.001 · QUR.RAG.002)

생성 프롬프트에는 질문, 앞 대화, 집계 값 절(분자·분모·산출 근거 포함), 그림 절, 근거 [1]…[n]
만 들어간다. 출력은 `{"answer": …}` JSON 하나로 묶어 경량 모델이 생각을 늘어놓는 길을 막는다.
수치 검문은 내보내기 전에 문장 단위로 한다(ARC-017, `app/rag/number_guard.py`).
- **근거로 인정하는 값:** 집계 값·그림 줄·근거 원문·목록 범위 줄에 있는 값. 값·단위가 같고, 문장(없으면 질문)의 대상어가 그 근거와 겹치고, 날짜가 있으면 기준 시점이 맞아야 통과한다.
- **근거가 아닌 것:** 질문과 앞 답의 숫자.
- **통과하지 못하면:** 그 문장 대신 안내 한 줄이 나가고 `NUMBER_GUARD` 가 남는다. 지어낸 숫자는 화면에도 저장 본문에도 없다.
- **수치로 보지 않는 숫자:** 각주·그림 표식, 날짜·시각, 버전·식별자, 절·목록·단계 번호.

### 7.6 출처 (SWFR.RAG.003 · RAG.006)

근거 청크마다 문서명·원문 위치·이동 링크를 `message_source` 에 저장하고 답 아래에 [n] 로
붙인다. 집계 값은 위젯과 같은 산출 근거 문장이 출처다.

### 7.7 후속 대화

같은 대화의 최근 3턴(질문·답 발췌 500자·그때의 지표·주제어)을 판정과 생성 양쪽에 준다.
"그 방법의 흐름을 보여줘", "그건 어떻게 해결해?" 처럼 혼자서는 주제가 없는 질문은 `followUp`
으로 표시되어 앞 답의 지표 또는 앞 답이 짚은 항목의 지표로 간다. 후속 판정은 캐시하지 않는다.
절차의 흐름을 그림으로 달라는 질문은 화면 그림이 아니라 "1) → 2) → 3)" 단계로 답한다.

### 7.8 모델을 부르는 곳

| 어디서 | 시키는 것 | 출력 |
|---|---|---|
| 질의 판정 (`rag/routing.py`) | 경로·지표·차원·템플릿·목록·후속 여부 | JSON 1개 |
| 답변 생성 (`rag/answer.py`) | 받은 재료로 문단 | `{"answer"}` |
| 위젯 생성 (`dashboard/generation.py`) | 지표·차원·템플릿·제목 | JSON 1개 |
| 문서 초안 유형 · 제목 (`document/draft_service.py`) | 22종 중 하나 · 제목 한 줄 | 코드 · 문장 |
| 속도 실측 (`ai/ollama_admin.py`) | 토큰 속도만 잰다 | 버림 |

수치·UI·요구사항을 만드는 호출은 없다. 모든 호출은 `LlmPort` 하나를 지나고, 서버 주소·모델·
`num_ctx`·`num_predict` 는 DB 활성 설정(`llm_setting`, `llm_model_cache`)이 정한다. 환경변수는
행이 없을 때만 쓴다(ARC-011).

임베딩 전용 모델은 답변 모델로 저장하지 않는다. 검색 모델은 환경변수로만 정하고, 색인과 모델이
다르면 문서 검색과 색인만 멈춘다(ARC-022).

### 7.9 라우팅 캐시 (ARC-014)

키는 `sha256(판정 프롬프트 전체 해시 + 답변 모델 설정 + 정규화한 질문)`. 답변 모델 설정은 서버 주소·모델·
`num_ctx`·`num_predict` 다(ARC-022). 판정만 캐시하고 값은 매번 새로 뽑는다.
프롬프트가 바뀌면 키가 바뀌어 옛 판정은 자연히 버려진다. 근거가 없어 막힌 판정과 현황으로
내려간 판정, 후속 판정은 저장하지 않는다.

---

## 8. 인포 템플릿과 대시보드 설계

*SWFR.WEB.001 · ARC-006 · ARC-012 · ARC-013*

### 8.1 템플릿 계약 (ARC-012)

인포 템플릿 23종은 화면 조각이 아니라 **입력 계약**이다. 템플릿마다 용도, 화면에 그려지는 것,
언제 고르는가, 받는 지표 값 유형, 차원 수 범위, 시간 축 요구, 범주 상한, 전체·목표·직전 구간
사용 여부, 옵션, 예시, 대화 사용 가능 여부, 그리고 사람이 "내용" 에 적을 예시 문장을 한 곳
(`widget_template.py`)에 적는다. 위젯 생성 프롬프트·질의 판정 프롬프트·저장 검증·관리자
쇼케이스가 모두 같은 정의를 읽는다.

| 가족 | 템플릿 |
|---|---|
| 수치 | 숫자 카드 · 스파크라인 · 불릿 차트 |
| 추이 | 추이 라인 · 면적 추이 · 누적 흐름 · 달력 히트맵 |
| 분포 | 막대 · 가로 막대 · 누적 막대 · 히트맵 · 파레토 · 트리맵 |
| 구성 | 파이 · 도넛 · 상태 흐름 · 레이더 |
| 변화 | 기울기 비교 · 순위 변화 |
| 점검 | 진행률 목록 · 점검표 · 표 · 간트 요약 |

### 8.2 위젯은 데이터

```
widget.spec_json = { template, title, prompt, query {measure, dimensions, filters, projectScope, limit}, options {unit, sort, threshold, stacked, showLegend, compareWithPrevious, columns} }
dashboard.layout_json = { lg: [{i, x, y, w, h, minW, minH}] }
```

프런트는 `spec → 렌더러` 한 단계로 그린다. 위젯을 만들 때 적은 의도(`prompt`)는 명세에 같이
저장돼 고칠 때 다시 보인다. 표·점검표는 보이는 열을 명세(`options.columns`)로 고르며, 이름 열이
있는 차원의 식별자 열은 기본으로 숨긴다.

### 8.3 위젯 생성

자연어 한 문장 → 모델이 지표·차원·템플릿·제목을 카탈로그에서 고름 → 서버가 계약에 맞는지
검증(안 맞으면 값 모양으로 기본 템플릿) → 미리보기 값을 시맨틱 레이어로 뽑음 → 사람이 배치.
카탈로그에 없는 것을 요구하면 `NOT_EXPRESSIBLE` 과 못 맞춘 용어를 돌려준다.

### 8.4 추천 구성

전체 진행 현황 · 이슈·위험 중심 · 산출물·요구사항 중심 · 전체(23종 쇼케이스) 네 구성이 있다.
위젯마다 의도 문장이 있고, 배치는 줄마다 12칸을 채우고 줄 높이를 맞춘다(숫자 카드·원형 차트는
넓이 상한, 마지막 줄은 왼쪽 정렬).

### 8.5 답변 속 그림 (ARC-013)

답변 본문의 `[그림 N]` 자리에 집계 블록(시맨틱 SQL) 또는 목록 블록(표준 모델 행)을 서버가
채운다. 값이 하나뿐이면 그림을 붙이지 않고 문장이 숫자를 말한다. 본문이 표식을 안 쓴 그림은
끝에 붙여 조용히 버리지 않는다.

---

## 9. 워크스페이스 설계

*SWFR.WEB.001~006 · QUR.WEB.001~003 · SER.SEC.003 · ARC-008*

### 9.1 역할

| 역할 | 볼 수 있는 것 | 할 수 있는 것 |
|---|---|---|
| `SUPER_ADMIN` | 전부 + 인포 템플릿 · 서버 오류 기록 · 모델 설정 · 발주기관·계정 | 플랫폼 운영, 발주기관 조직과 담당자 계정 발급·중지, 사업 관리. **업무 판단은 하지 않는다**(ARC-032) |
| `CLIENT` (발주기관) | 자기 조직 사업 전부 | 사업 생성·용역사 할당·도구 연동·수집 설정·대시보드 편집. 업무 판단: 요구사항 목록 확정·돌려보내기, 상태 지정, 산출물 승인·반려, 확인 요청·확인완료·재요청, 작업 완료 확인 |
| `CONTRACTOR` (용역사) | 할당된 사업만 | 산출물·자료 업로드. 업무 행위: 요구사항 명세서 등록·정리·제출, 조치 보고, 작업 완료 보고. 현황 화면은 읽기 전용 |

발주기관 화면에는 원천 데이터를 고치는 기능이 없다(QUR.WEB.001). 수집 설정은 용역사에게
보이지 않는다.

**계정이 생기는 길 (11-02, GH-187)**

- 발주기관: 최고관리자가 `발주기관·계정`(`/admin/accounts`)에서 조직을 만들고 담당자 계정을 발급한다. 첫 비밀번호는 서버가 만들어 발급 응답에 한 번만 담는다. 저장은 해시로만 하고 변경 이력에는 아이디와 기관 이름만 남긴다. 받은 사람은 로그인한 뒤 사용자 메뉴의 `비밀번호 바꾸기`(`POST /api/auth/password`)로 바꾼다.
- 용역사: 사업의 초대 링크로 가입한다. 조직은 그때 생긴다. 관리자 화면에서는 만들지 않는다.
- 사업은 발주기관 계정이 자기 기관 이름으로 만든다. 그래서 사업을 만들 때 발주기관을 고르는 칸은 두지 않는다.
- 계정은 지우지 않고 중지한다. 판정·승인 기록의 행위자가 남아야 한다. 중지하면 로그인과 토큰 갱신이 막히고, 이미 받은 접근 토큰은 유효 시간이 지나면 끝난다.
- 조직·사용자 관리 전반(권한 위임, 외부 인증 연동)은 IM-001 10절 제외 범위로 남는다. 여기 있는 것은 PoC 운영에 필요한 발급·중지뿐이다.

### 9.2 화면

| 메뉴 | 경로 | 원천 |
|---|---|---|
| 사업 목록 | `/projects` | `project` + 요약 지표 · 미처리 확인 요청 수 |
| 진행 상황 | `/p/:id/dashboard` | 대시보드 · 위젯(시맨틱 레이어) |
| 일정 | `/p/:id/schedule` | `wbs_item` (원천 WBS_FILE · REDMINE · NONE 표시) |
| 스냅샷 | `/p/:id/snapshots` | `progress_snapshot` 추이 + 전일 대비 |
| 이슈 · 위험 | `/p/:id/issues` | `issue` `risk` |
| 요구사항 | `/p/:id/traceability` | `requirement` + `trace_link` |
| 확인 요청 | `/p/:id/reviews` | `review_request` |
| 산출물 | `/p/:id/deliverables` | `wbs_item` 판정 목록 + 항목별 업로드. 22종 점검표는 접힘 |
| 자료 | `/p/:id/documents`, `/documents/:id` | `document_upload`, 추출 원문 |
| AI 질의 | `/ask`, `/p/:id/ask` | 대화 · 메시지 · 출처 |
| 사업 설정 | 사업 정보 · 용역사 할당 · 도구 연동 · 동기화 이력(수집·스냅샷 설정 대화상자) | |
| 관리자 | 인포 템플릿 `/templates` · 서버 오류 기록 `/admin/errors` · 설정 | |

### 9.3 확인 요청과 조치 보고 (SWFR.WEB.004~006, ARC-008)

대상 5종(WBS 항목 · 산출물 · 이슈 · 리스크 · 지표)을 짚어 요청하면 **등록 시점 상태**를
`snapshot_json` 에 떠 둔다. 용역사가 보고하면 보고 시점 상태를 다시 떠 두 상태의 차이를 보고
내용 옆에 나란히 보인다. 상태는 REQUESTED → REPORTED → CONFIRMED, 재요청은 같은 요청 안에서
순환한다. 요청·확인·재요청은 발주기관만, 보고는 용역사만(불일치 403). 원천 도구에는 아무것도
쓰지 않는다(QUR.WEB.003).

### 9.5 담당 사업 목록과 요약 (SWFR.WEB.003)

`/projects` 는 호출자가 볼 수 있는 사업만 보인다(발주기관은 자기 조직 사업 전부, 용역사는 할당된 사업,
플랫폼 관리자는 전부, 10절 인가). 한 줄에 사업마다 아래를 서버가 센다(`ProjectSummaryResponse`).

| 칸 | 원천 |
|---|---|
| 사업명 · 상태 · 기간 · 단계 · 용역사 | `project` · 할당 |
| 필수 산출물 승인/전체 | `work_product` 현행 버전 |
| 열린 시정조치 · 열린 리스크 | `correction_action` · `risk` |
| 미처리 확인 요청 | `review_request`(SWFR.WEB.006) |

**아직 없는 것:** 사업별 진척률·마일스톤 요약 칸. 진척은 사업 첫 화면(9.2 진행 상황)에서 본다.
목록에 넣을지는 일정 준수율(13.3절)과 함께 정한다.

### 9.6 원천 데이터를 고치는 기능 없음 (QUR.WEB.001)

발주기관 화면은 원천 도구의 데이터를 바꾸지 않는다. 세 곳에서 막는다.

- **커넥터:** 어댑터는 GET 만 부른다. `tests/test_readonly_guard.py` 가 어댑터 소스에 다른 HTTP
  메서드가 있으면 CI 를 실패시킨다(4.4절).
- **API:** 표준 모델(`requirement` `issue` `code_change` `risk`)을 바꾸는 API 가 없다. 표준 모델은 수집과
  승격만 쓴다. 산출물 승인·반려(`…/work-products/{id}/approve` `reject`)는 AX Link 안의 검토 기록이고
  원천 도구에 쓰지 않는다.
- **화면:** 요구사항·이슈·커밋 칸에 편집 기능을 두지 않는다. 원천을 고쳐야 하면 도구에서 고치고 다음
  수집에서 반영된다. 확인 요청·조치 보고도 AX Link 안에만 남는다(QUR.WEB.003).

### 9.4 활동 기록과 알림

`activity_event` 한 표에 종류(확인 요청·보고·확인, 문서 업로드, 산출물 제출·지연, 수집 실패·변경,
스냅샷)와 대상 역할(CLIENT · CONTRACTOR · ALL · LOG)을 적는다. 상대 역할에게 알릴 사건은
알림 종에 뜨고(`notification_seen` 으로 읽음 관리), LOG 는 기록만 남는다. 기록은 최선 노력이라
본 작업을 막지 않는다.

---

## 10. 보안 설계

*SER.SEC.001~003 · QUR.RAG.001*

| 항목 | 설계 |
|---|---|
| 인증 | 아이디·비밀번호(bcrypt) → JWT 액세스 + 리프레시 토큰(`refresh_token`). 초대 링크로 가입 |
| 인가 | 역할 + 사업 할당. 모든 사업 범위 API 는 호출자의 접근 사업과 교차한 뒤 실행. 업무 판단은 행위별 권한표(`app/auth/duties.py`, ARC-032)를 따른다. 플랫폼 관리자도 판단 행위는 403 이다(DEC-05) |
| 자격증명 | 도구 토큰은 `common/crypto.py` 로 암호화해 저장. 화면·로그에 내지 않고 연결 확인 응답에도 없다 |
| 원천 무변경 | 어댑터 정적 검사 + 읽기 권한 토큰(4.4절) |
| 폐쇄망 | 앱 이미지 둘 + 컴포즈 + 모델 파일이 반입 요소. 외부 호출은 원천 도구와 Ollama 뿐. 스케줄러가 서버 안에 있어 cron 반입이 없다 |
| 오류 | 처리되지 않은 예외는 `app_error_log` 에 사용자 id 와 함께 남고 관리자 화면에서 본다 |

---

## 11. API 목록

경로는 전부 `/api` 아래다. 인증은 `Authorization: Bearer`.

| 영역 | 경로 |
|---|---|
| 인증 | `POST /auth/login` `/auth/refresh` `/auth/logout` · `GET /auth/me` · `GET /auth/invitations/{token}` · `POST /auth/invitations/accept` |
| 사업 | `GET/POST /projects` · `GET/PATCH/DELETE /projects/{id}` · `GET/POST …/assignments` · `POST …/invites` · `GET/PUT …/schedule` |
| 연계 | `GET /projects/{id}/connections` · `POST /connections/test` · `PATCH /connections/{id}` `…/mapping` `…/status` · `DELETE` · `POST /connections/{id}/sync` · `POST /sync-jobs/{id}/retry` · `GET /sync-jobs` |
| 표준 | `GET /projects/{id}/requirements[/{rid}]` `…/issues` `…/work-products` `…/traceability` |
| 진척 | `GET /projects/{id}/progress` `…/wbs` `…/wbs/deliverables` · `GET/POST …/snapshots` |
| 대시보드 | `GET /dashboards` · `GET /dashboards/{id}` · `PUT …/layout` · `POST …/widgets` · `PATCH/DELETE /widgets/{id}` · `POST /widgets/{id}/data` · `POST /widgets/preview` · `POST /widgets/generate` · `GET /widget-templates` · `GET /semantic/catalog` |
| 문서 | `POST /projects/{id}/documents` · `GET/PATCH/DELETE /documents/{id}` · `GET …/text` `…/chunks` `…/content` `…/draft` · `POST …/draft/confirm` `…/draft/reject` |
| 질의 | `GET/POST /conversations` · `GET /conversations/suggestions` · `PATCH/DELETE /conversations/{id}` · `GET/POST …/messages`(SSE) · `POST /messages/{id}/feedback` |
| 확인 요청 | `GET /projects/{id}/review-targets` · `GET/POST …/review-requests` · `GET /review-requests/{id}` · `POST …/report` `…/confirm` `…/rerequest` |
| 활동 | `GET /projects/{id}/activity` · `GET /notifications` · `POST /notifications/seen` |
| 모델 | `GET/PUT /ai/settings` · `POST /ai/models/refresh` `…/measure` · `PUT /ai/models/params` |
| 관리 | `GET/DELETE /admin/errors` · `GET /users` |

---

## 12. 요구사항 대응표

설계 문서 열은 각 ARC 머리 표의 `관련` 행에서 그대로 옮겼다(10-13 대조). 확정 ARC 가 없는 요구사항은
이 문서의 해당 절이 설계 근거다. 이 문서는 아직 초안이다.

| 요구사항 | 설계 절 | 설계 문서(ARC 관련 행) |
|---|---|---|
| SWFR.CON.001 커넥터 공통 인터페이스 | 4.1 | ARC-003 |
| SWFR.CON.002 매핑을 설정으로 | 4.2 | ARC-005 |
| SWFR.CON.003 GitHub 수집 | 4.1 | ARC-003 |
| SWFR.CON.004 Redmine 수집 | 4.1 | ARC-003 |
| SWFR.CON.005 증분 · 재현 | 4.3 · 4.5 | ARC-003 |
| SWFR.CON.006 인증정보 등록 · 연결 확인 | 4.7 · 10 | - (확정 ARC 없음) |
| QUR.CON.001 읽기 전용 | 4.4 | ARC-003 · ARC-004 |
| SWFR.CON.007 문서 추출 | 4.6 · 6.1 | ARC-009 · ARC-021 |
| SWFR.PIP.001 29110 관리 객체 | 3.3 | ARC-005 · ARC-009 |
| SWFR.PIP.002 표준화 · 원천 보존 | 3.1 · 5.1 | ARC-005 · ARC-009 |
| SWFR.PIP.003 추적관계 생성 | 5.3 | ARC-007 · ARC-016 · ARC-024 |
| SWFR.PIP.004 근거 보존 | 5.3 | ARC-007 · ARC-024 |
| QUR.PIP.001 근거 없는 관계 금지 | 3.1 · 5.3 | ARC-007 · ARC-024 |
| SWFR.PIP.005 일별 스냅샷 | 4.5 · 5.8 | ARC-006 |
| SWFR.PIP.006 진척 지표 | 5.4 | ARC-006 · ARC-016 · ARC-019 · 진척률-산정체계 |
| SWFR.PIP.007 일정 준수율 | 13.3 (미결) | ARC-006 |
| SWFR.PIP.008 품질 지표 | 5.6 · 5.9 | ARC-006 · ARC-025 |
| SWFR.PIP.009 산출물 지표 | 5.5 · 5.9 | ARC-005 · ARC-006 · ARC-016 · ARC-019 |
| SWFR.PIP.010 WBS 파싱 · 산출물 근거 | 5.4 · 5.5 | ARC-016 · 진척률-산정체계 |
| SWFR.WEB.001 한 화면 현황 | 8 · 9.2 | ARC-006 · ARC-011 · ARC-012 · ARC-013 · ARC-016 · ARC-018 |
| SWFR.WEB.002 추적관계 조회 | 5.3 · 9.2 | ARC-007 · ARC-018 · ARC-024 |
| SWFR.WEB.003 복수 사업 목록 | 9.5 | - (확정 ARC 없음) |
| QUR.WEB.001 원천 수정 금지 | 9.6 · 9.1 | - (확정 ARC 없음) |
| QUR.WEB.002 관리 용어 · 산출 근거 | 1.2(9) · 5.7 | ARC-018 |
| SWFR.WEB.004 확인 요청 등록 | 9.3 | ARC-008 · ARC-016 · ARC-019 |
| SWFR.WEB.005 조치 보고 · 변경 내역 | 9.3 | ARC-008 · ARC-019 |
| SWFR.WEB.006 상태 관리 · 역할 | 9.3 | ARC-008 · ARC-019 |
| QUR.WEB.003 내부 기록만 | 9.3 | ARC-008 |
| SWFR.RAG.001 온프레미스 LLM 응답 | 7.1 · 7.5 | ARC-010 · ARC-011 · ARC-012 · ARC-013 · ARC-014 · ARC-015 |
| SWFR.RAG.002 모델 호출 인터페이스 분리 | 2.2 · 7.8 | ARC-011 · ARC-022 |
| QUR.RAG.001 클라우드 비의존 | 2.1 · 10 | ARC-011 · 인프라-배치방안 |
| SWFR.RAG.003 청킹 · 원문 위치 | 6.1 | ARC-009 · ARC-010 |
| SWFR.RAG.004 한국어 임베딩 · 유사도 검색 | 6.1 · 7.4 | ARC-010 |
| SWFR.RAG.005 검색 + 집계 결합 | 7.2 · 7.7 | ARC-010 · ARC-012 · ARC-013 · ARC-014 · ARC-015 · ARC-020 |
| SWFR.RAG.006 출처 제시 | 7.6 | ARC-010 |
| SWFR.RAG.007 근거 부족 차단 | 7.3 | ARC-010 · ARC-013 · ARC-015 · ARC-017 · ARC-020 · ARC-022 |
| QUR.RAG.002 수치는 집계에서만 | 1.1 · 7.5 | ARC-009 · ARC-010 · ARC-013 · ARC-014 · ARC-015 · ARC-017 · ARC-020 |
| SWFR.DEM.001 전 과정 한 시스템 | 2.6 · 2.4 | - (확정 ARC 없음) |
| SER.SEC.001 자격증명 암호화 | 10 | - (확정 ARC 없음) |
| SER.SEC.002 폐쇄망 설치 | 10 · 2.1 | 인프라-배치방안 · 40-manual/폐쇄망-반입-목록 |
| SER.SEC.003 역할 구분 · 사업 범위 | 9.1 · 10 | ARC-008 · ARC-010 |

---

## 13. 검증 계획과 미결

### 13.1 완료로 적기 전에 확인할 것

| 항목 | 상태 | 확인 방법 |
|---|---|---|
| 하이브리드 검색(7.4) | 구현됨. 검색이 빗나가는 경우가 있다 | 질문 묶음으로 적중률을 재고 `rag_min_similarity`·RRF 후보 수를 조정한다(ARC-015 방식) |
| 근거 게이트(7.3) | 구현됨. 문턱 0.55 는 문서 5건으로 잰 값 | 근거 있는 질문·없는 질문 각 묶음으로 차단·통과율을 잰다 |
| Redmine 커넥터(4.1) | 구현됨. 실 서버 수집 시험 미완 | Redmine 컨테이너로 증분 수집 2회 후 표준 엔터티·추적관계 대조 |
| 시험 통과율(5.9) | CI 성공률로 대신하고 있다 | 시험 결과 원천을 정한 뒤 지표 재정의(M4) |

### 13.2 미결

- 일정 준수율(SWFR.PIP.007): 13.3절.
- 이슈에서 WBS 번호를 라벨 없이 추정하지 않는다는 결정(ARC-016)은 유지한다. 대신 이슈 생성
  시점의 라벨 규약을 용역사 안내에 넣는다.
- 관리 객체 중 표만 있는 다섯(변경요청 · 시정조치 · 회의록 · 검수확인 · 진척기록)의 원천.
- 두 지표를 한 답에서 비교하는 질문(7.2)은 지표 하나를 고르는 구조라 아직 한쪽만 답한다.
- GPU 서버 사양과 폐쇄망 차단 범위(인프라-배치방안 5절).

---

### 13.3 일정 준수율 (SWFR.PIP.007 미결)

요구사항 원문은 "마일스톤 달성 기준으로 일정 준수율을 산출"이다. **산식과 원천이 정해지지 않아 설계를
끝내지 않았다.** 지금은 ARC-006 이 WBS 계획선 대비 편차(`behind_task_count`, 계획선 대비 편차)로
대신 보이고 있고, 그것은 요구사항이 말한 지표가 아니다.

알고 있는 것:
- GitHub 마일스톤은 원본으로 수집된다(이름·기한·상태·닫힌 시각). 표준 모델과 화면에는 아직 없다
  (GH-130, 초안 ARC-023 은 이름·기한·상태 표시만 다루고 준수율은 다루지 않는다).
- Redmine 은 버전(Version)이 마일스톤이다(작업 규약 2절). 버전도 원본으로 수집된다.

사용자가 정해야 할 것:
1. 무엇을 "달성"으로 보는가: 마일스톤이 기한 안에 닫힘 / 마일스톤에 묶인 이슈가 기한 안에 모두 닫힘 /
   WBS 항목 기준.
2. 준수율의 분모: 기한이 지난 마일스톤만 / 전체.
3. 기한이 없는 마일스톤, 기한 뒤에 다시 연 마일스톤의 처리.
4. GitHub 마일스톤과 Redmine 버전이 함께 있을 때 어느 쪽을 원천으로 하는가.
5. WBS 계획선 대비 편차를 함께 보일지, 대체할지.

정해지면 별도 ARC 로 확정하고 이 절과 ARC-006 관련 행의 "미결" 표시를 지운다.

## 부록. 설계 문서 목록

| 코드 | 제목 | 확정 |
|---|---|---|
| ARC-001 | 백엔드 구현 언어 파이썬 전환 | 08-27 |
| ARC-002 | 추적 ID 체계를 요구사항 코드로 통일 | 09-08 |
| ARC-003 | 도구 연동 방식: REST 직접 호출로 통일 | 09-09 |
| ARC-004 | 커넥터 읽기 전용 보장의 검증 방법 | 09-09 |
| ARC-005 | 표준 데이터 모델: ISO/IEC 29110 관리 객체 정의 | 09-10 |
| ARC-006 | 시맨틱 레이어와 위젯 데이터, 일별 스냅샷 | 09-14 |
| ARC-007 | 추적관계 생성 규칙 | 09-14 |
| ARC-008 | 확인 요청과 조치 보고 | 09-14 |
| ARC-009 | 문서 정형화 초안 | 09-14 |
| ARC-010 | 자연어 질의 처리 방식 | 09-14 |
| ARC-011 | LLM 모델별 토큰 설정 | 09-16 |
| ARC-012 | 인포 템플릿 카탈로그 | 09-17 |
| ARC-013 | 답변에 인포 템플릿 대입 | 09-17 |
| ARC-014 | 라우팅 캐시 | 09-17 |
| ARC-015 | 일반 질문의 답변율: 현황 경로와 측정 | 09-17 |
| ARC-016 | WBS 중심 관리 모델 | 09-21 |
| ARC-017 | 근거 게이트와 수치 검문 강화 | 10-02 |
| ARC-018 | 일반 이슈의 집계 범위와 요구사항 상태 출처 표시 | 10-02 |
| ARC-019 | 작업 완료 확인과 완료 확인율 | 10-06 |
| ARC-020 | 답의 종류와 일정 질문 | 10-07 |
| ARC-021 | 문서 처리 대기열 | 10-07 |
| ARC-022 | 답변 모델과 검색 모델 분리 | 10-07 |
| ARC-023 | 일반 이슈의 원천 마일스톤 표시 (초안) | 10-08 |
| ARC-024 | 설계 근거 연결과 변경 분류 | 10-13 |
| ARC-025 | 요구사항 상태: 근거 상태와 발주기관 지정 (초안) | 10-14 |
| ARC-032 | 플랫폼 관리와 업무 판단 권한 분리 | 11-16 |
| ARC-033 | WBS 작업별 산출물·양식 지정 | 11-16 |
| ARC-034 | AI 판단 답변 방식 (초안) | 11-25 |
| - | 진척률 산정 체계 | 08-27 (09-15 추가, 11-16 L3 DEC-17) |
| - | 인프라 배치 방안 | 08-21 (v0.1) |
