# AX-Link 물리 설계 — 백엔드 물리 구조

> **2026-08-21 범위 확정**: 연동 도구는 형상관리 **GitHub** · 프로젝트 관리 **Redmine** 2종으로 확정했다.
> 이 문서의 Jira · GitLab · Notion 관련 서술은 그 시점 이전 기록이며 더 이상 유효하지 않다.
> 현재 범위는 `docs/AX-Link-PRD.md` §1.4 와 `docs/design/02-logical-datamodel.md` §3.5 를 따른다.


| 항목 | 내용 |
| --- | --- |
| 문서 ID | `design/03-physical-backend` |
| 버전 | v1.0 (2026-08-20) |
| 상위 문서 | `01-conceptual-architecture.md`, `02-logical-api.md`, `02-logical-datamodel.md` |
| 지위 | **구현 에이전트가 그대로 만드는 백엔드 청사진.** 여기 적힌 좌표·패키지·클래스명·메서드 시그니처·설정 키를 그대로 쓴다 |
| 범위 | `backend/` 모듈 전체. 프론트는 `02-logical-frontend` 소관 |

---

## 0. 선행 문서와의 충돌 해소 (3건)

선행 3문서가 서로 다르게 적은 지점이다. **이 표의 결론이 구현 기준**이며, 아래 본문 전체가 이 결론 위에 서 있다.

| # | 충돌 | 채택 | 근거 |
| --- | --- | --- | --- |
| C-1 | 영속화 방식 — 아키텍처 §2.2 는 "Spring Data JPA", 데이터모델 §0.3 은 `@PreUpdate`·`@Enumerated` 를 전제 | **Spring JDBC `JdbcClient` 단독. JPA·Hibernate 를 쓰지 않는다** | ① 시맨틱 레이어는 카탈로그 조각으로 SQL 을 조립해 실행하는 것이 본질이라 JPQL·Criteria 로 표현할 수 없고, 결국 `JdbcTemplate` 병행이 된다 — 두 영속 스택을 동시에 유지할 이유가 없다. ② `vector(1024)`·`tsvector`·부분 유니크 `on conflict`·`pg_trgm` 은 전부 네이티브 SQL 이 필요하다. ③ 다형 참조 3곳(`trace_link`·`entity_history`·`doc_chunk`)은 FK 가 없어 연관 매핑 이득이 없다. ④ 1차 규모(최대 테이블 60만 행, 목록 조회 중심)에 영속성 컨텍스트·더티체킹이 주는 이득보다 N+1·flush 순서 디버깅 비용이 크다. **대가**: `updated_at` 자동 갱신이 사라지므로 §2.4 의 UPDATE 규칙으로 대체한다 |
| C-2 | enum 와이어 표기 — API §1.8/§3.0 은 표준 엔티티 상태를 소문자(`defined`,`bar-chart`), 데이터모델 §3.6 은 CONSTANT_CASE(`DEFINED`,`BAR_CHART`) | **전 계층 CONSTANT_CASE 단일 표기.** API 문서 §3.0 의 소문자·케밥 리터럴은 CONSTANT_CASE 로 정정해 프론트 `standard/` 에 반영한다 | 데이터모델 §3.6 이 이미 명시적 근거(INV-18 3자 일치 테스트를 단일 규칙으로 실행)를 들어 확정했다. 소문자 와이어를 유지하면 Java enum ↔ 와이어 ↔ DB 사이에 enum 15종짜리 양방향 변환기가 생기고, INV-18 테스트가 "값 집합 비교"가 아니라 "매핑표 비교"가 되어 규칙이 둘로 늘어난다. Jackson 기본 enum 직렬화를 그대로 쓰면 변환 코드가 0줄이다 |
| C-3 | Anthropic Java SDK 선택적 의존 | **의존성에 넣지 않는다** | 공통 컨텍스트·ADR-003·INV-35 가 "어댑터는 Ollama·Fake 딱 2벌"을 못 박았고, ArchUnit 테스트가 `LlmPort` 구현체 개수 == 2 를 강제한다. 쓰지 않을 SDK 를 클래스패스에 두면 그 테스트와 정면 충돌한다. 나중에 필요해지면 `kr.co.axlink.ai.port` 인터페이스는 이미 공급자 중립이므로 `com.anthropic:anthropic-java` 를 추가하고 `ai.adapter.anthropic` 패키지 하나만 만들면 된다 — 호출부는 손대지 않는다. 좌표를 지금 고정하지 않는 이유는 추가하지 않을 의존성의 버전은 관리 대상이 아니기 때문이다 |

추가 정정 1건 — **Jira 검색 엔드포인트**: API §7.2 시퀀스는 `POST /rest/api/3/search` 로 그렸으나 해당 엔드포인트는 폐기되었다. 구현은 `POST /rest/api/3/search/jql` + `nextPageToken` 커서 페이지네이션을 쓴다(§4.4).

---

## 1. 빌드 구성

### 1.1 모듈 레이아웃

```
ax-link/
  settings.gradle
  build.gradle                    ← 루트는 backend 하나만 포함. 멀티모듈로 쪼개지 않는다
  gradle/wrapper/                 gradle-8.14.2-bin.zip
  backend/
    build.gradle
    src/main/java/kr/co/axlink/...
    src/main/resources/
      application.yml
      db/migration/V1__extensions.sql ... V10__history_grants.sql
    src/test/java/kr/co/axlink/...
    src/test/resources/
      application.yml               ← axlink.ai.provider: fake 고정
      fixtures/jira/*.json, fixtures/gitlab/*.json
  frontend/                        ← 별도 npm 워크스페이스. Gradle 이 관여하지 않는다
```

`settings.gradle`
```groovy
rootProject.name = 'ax-link'
include 'backend'
```

프론트를 Gradle 태스크로 묶지 않는다. `npm run dev` 와 `./gradlew bootRun` 을 각각 띄우고 Vite dev proxy(`/api` → `localhost:8080`)로 연결한다 — 빌드 그래프를 하나로 묶으면 백엔드 단독 테스트에도 node 설치가 필요해진다.

### 1.2 `backend/build.gradle` 전문

```groovy
plugins {
  id 'java'
  id 'org.springframework.boot'          version '3.3.13'
  id 'io.spring.dependency-management'   version '1.1.7'
}

group = 'kr.co.axlink'
version = '0.1.0'

java {
  toolchain { languageVersion = JavaLanguageVersion.of(17) }
}

repositories { mavenCentral() }

dependencies {
  implementation 'org.springframework.boot:spring-boot-starter-web'
  implementation 'org.springframework.boot:spring-boot-starter-validation'
  implementation 'org.springframework.boot:spring-boot-starter-security'
  implementation 'org.springframework.boot:spring-boot-starter-jdbc'
  implementation 'org.springframework.security:spring-security-oauth2-jose'

  implementation 'org.flywaydb:flyway-core'
  implementation 'org.flywaydb:flyway-database-postgresql'

  implementation 'org.apache.tika:tika-core:2.9.2'
  implementation 'org.apache.tika:tika-parsers-standard-package:2.9.2'
  implementation 'kr.dogfoot:hwplib:1.1.4'
  implementation 'kr.dogfoot:hwpxlib:1.0.5'

  runtimeOnly 'org.postgresql:postgresql'

  annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

  testImplementation 'org.springframework.boot:spring-boot-starter-test'
  testImplementation 'org.springframework.security:spring-security-test'
  testImplementation 'com.tngtech.archunit:archunit-junit5:1.3.0'
}

tasks.named('test') {
  useJUnitPlatform()
  systemProperty 'spring.profiles.active', 'test'
}

tasks.named('bootJar') { archiveFileName = 'axlink.jar' }
```

### 1.3 의존성 채택 근거와 미채택 목록

| 좌표 | 버전 | 채택 이유 |
| --- | --- | --- |
| `spring-boot-starter-web` | BOM | REST + `SseEmitter`(§6.6). WebFlux 를 쓰지 않는다 — SSE 중계 1개 때문에 전 계층을 리액티브로 바꿀 이유가 없다 |
| `spring-boot-starter-validation` | BOM | Bean Validation. `ErrorResponse.details.fieldErrors` 의 원천 |
| `spring-boot-starter-security` | BOM | 필터체인·`@PreAuthorize`·`BCryptPasswordEncoder` |
| `spring-boot-starter-jdbc` | BOM | `JdbcClient`(Boot 3.2+ 자동설정) + HikariCP + `DataSourceTransactionManager` |
| `spring-security-oauth2-jose` | BOM | `NimbusJwtEncoder`/`NimbusJwtDecoder` (HS256). **jjwt 를 쓰지 않는 이유**: 이미 Spring Security 를 쓰는데 JWT 서명·검증만 별도 라이브러리의 별도 버전으로 관리할 이유가 없다. BOM 이 버전을 관리한다 |
| `flyway-core` + `flyway-database-postgresql` | BOM | Flyway 10 부터 PostgreSQL 지원이 별 모듈이라 둘 다 필요 |
| `tika-core` + `tika-parsers-standard-package` | 2.9.2 | PDF·DOCX·XLSX 를 `AutoDetectParser` 하나로 처리. PDFBox·POI 를 직접 붙이면 포맷별 분기 코드가 생긴다 |
| `hwplib` / `hwpxlib` | 1.1.4 / 1.0.5 | HWP·HWPX 는 Tika 미지원. 국내 산출물 필수 포맷(PRD §2.1) |
| `postgresql` | BOM | JDBC 드라이버. `runtimeOnly` — 컴파일 타임에 참조하는 코드가 없다 |
| `archunit-junit5` | 1.3.0 | INV-04·INV-26·INV-35 가 명시적으로 아키텍처 테스트를 요구한다. 테스트 스코프 전용 |

**미채택 (추가하지 않는다)**

| 좌표 | 대신 쓰는 것 |
| --- | --- |
| `com.anthropic:anthropic-java`, OpenAI SDK 류 | §0 C-3. Ollama 어댑터 + Fake 어댑터 2벌 |
| `com.pgvector:pgvector` (Java 바인딩) | `float[]` → `"[0.1,0.2,...]"` 문자열로 바인딩하고 SQL 에서 `:qvec::vector` 로 캐스트. `VectorCodec` 12줄(§6.3) |
| `com.networknt:json-schema-validator` 등 JSON Schema 라이브러리 | jsonb 스키마 검증은 **record 역직렬화 실패 = 검증 실패**(데이터모델 §5.0 말미). `@JsonIgnoreProperties(ignoreUnknown = false)` + Bean Validation |
| `org.springframework.retry:spring-retry` | 백오프가 필요한 지점이 커넥터 1곳뿐. `common.support.Backoff` 30줄 |
| `spring-boot-starter-data-jpa` | §0 C-1 |
| `testcontainers` | 로컬 PostgreSQL `axlink_test` DB(§8.2) |
| `springdoc-openapi` | `02-logical-api.md` 가 계약 문서다. 런타임 스펙 생성기를 이중으로 두지 않는다 |
| Lombok | 공통 컨텍스트 금지 항목. DTO 는 record, 엔티티는 record 또는 필드 + 생성자 |

---

## 2. 패키지 트리와 클래스 목록

### 2.0 읽는 법 · 전역 규칙

| 규칙 | 내용 |
| --- | --- |
| 패키지 | `kr.co.axlink.<도메인>.{web|service|domain|repository}`. 도메인 목록은 아키텍처 §2.3 확정값 |
| DI | 전 클래스 **생성자 주입**. 필드 주입·`@Autowired` 애노테이션·Lombok 금지. 생성자가 1개면 애노테이션도 생략 |
| DTO | 전부 `record`. 필드명·순서는 `02-logical-api.md` §3 과 1:1. 아래 표는 이름만 나열하고 필드를 반복하지 않는다 |
| 트랜잭션 | `@Transactional` 은 `*.service` 클래스에만. 조회 서비스 메서드는 `@Transactional(readOnly = true)` |
| 주석 | 코드에 주석을 쓰지 않는다 |
| 행 매핑 | 기본은 `jdbcClient.sql(...).param(...).query(XxxRow.class).list()` — `DataClassRowMapper` 가 record + snake_case→camelCase + String→enum 을 처리한다. **손으로 매퍼를 쓰는 경우는 셋뿐**: `jsonb` 컬럼, 배열 컬럼(`uuid[]`/`text[]`), `vector` 컬럼. 그때만 `RowMappers` 내부 static 메서드를 둔다 |
| 반환 타입 | Repository 는 도메인 record(또는 `XxxRow` 프로젝션)를 반환한다. `Map<String,Object>` 를 서비스로 넘기지 않는다 |
| 권한 인자 | 프로젝트 종속 조회 메서드는 시그니처에 `Collection<UUID> projectIds` 를 **필수 인자**로 갖는다. 이 인자 없는 목록 조회 메서드를 정의하지 않는다 (INV-04, ArchUnit 검증) |

### 2.1 `kr.co.axlink` (1)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `AxLinkApplication` | Config | `@SpringBootApplication`, `@ConfigurationPropertiesScan` | `static void main(String[])` |

### 2.2 `kr.co.axlink.config` (6)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `SecurityConfig` | Config | 필터체인·`PasswordEncoder`·`JwtEncoder`/`JwtDecoder` 빈. `@EnableMethodSecurity` | `SecurityFilterChain filterChain(HttpSecurity, JwtAuthenticationFilter)`<br>`PasswordEncoder passwordEncoder()`<br>`JwtEncoder jwtEncoder(JwtProperties)`<br>`JwtDecoder jwtDecoder(JwtProperties)` |
| `WebConfig` | Config | CORS(dev 한정), 멀티파트 상한, `@RestControllerAdvice` 외 MVC 설정 | `void addCorsMappings(CorsRegistry)`<br>`MultipartConfigElement multipartConfig()` |
| `AsyncConfig` | Config | 비동기 실행기 3종 빈 | `TaskExecutor syncExecutor()` (2 threads, queue 32)<br>`TaskExecutor documentExecutor()` (2, 64)<br>`TaskExecutor ragExecutor()` (8, 32)<br>`ScheduledExecutorService sseHeartbeatScheduler()` (1) |
| `SchedulingConfig` | Config | `@EnableScheduling` + 스케줄러 풀(2) | `ThreadPoolTaskScheduler taskScheduler()` |
| `AiPortConfiguration` | Config | `LlmPort`·`EmbeddingPort` 구현체 선택 **단일 지점** (INV-35) | `LlmPort ollamaLlmPort(AiProperties, ObjectMapper)` `@ConditionalOnProperty(havingValue="ollama", matchIfMissing=true)`<br>`LlmPort fakeLlmPort()` `@ConditionalOnProperty(havingValue="fake")`<br>동일 조건으로 `EmbeddingPort` 2건<br>`HttpClient ollamaHttpClient(AiProperties)` |
| `ClockConfig` | Config | `Clock` 빈(UTC). 기한·지연 판정 테스트 고정용 | `Clock clock()` → `Clock.systemUTC()` |

### 2.3 `kr.co.axlink.common.error` (5)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `ErrorCode` | enum | API §1.5 전 코드 + HTTP 상태 보유 | `HttpStatus status()`, `String defaultMessage()` |
| `ErrorResponse` | record DTO | `(String code, String message, Map<String,Object> details, String path, Instant timestamp)` | `static ErrorResponse of(ErrorCode, String, Map, String)` |
| `ApiException` | Exception | 전 도메인 예외의 단일 상위. `ErrorCode` + `details` 보유 | `ErrorCode code()`, `Map<String,Object> details()` |
| `ApiExceptions` | Factory | 예외 생성 정적 팩토리. 예외 클래스를 코드별로 만들지 않는다 | `static ApiException projectAccessDenied()`<br>`static ApiException notFound(String entity, UUID id)`<br>`static ApiException invalidTransition(Enum<?> from, Enum<?> to)`<br>`static ApiException catalogValidationFailed(String reason)`<br>`static ApiException toolAuthFailed(int toolStatus, String toolMessage)` … (ErrorCode 1:1) |
| `GlobalExceptionHandler` | Config | `@RestControllerAdvice`. 전 예외 → `ErrorResponse` 단일 형태 | `ResponseEntity<ErrorResponse> handleApi(ApiException, HttpServletRequest)`<br>`… handleValidation(MethodArgumentNotValidException, …)`<br>`… handleDuplicate(DuplicateKeyException, …)`<br>`… handleMaxUpload(MaxUploadSizeExceededException, …)`<br>`… handleFallback(Exception, …)` |

**예외 클래스를 코드마다 만들지 않는 이유**: `ErrorCode` 25종에 예외 클래스 25개를 만들면 핸들러가 25개 `@ExceptionHandler` 가 된다. 코드가 데이터인 이상 예외도 하나면 충분하다. 스택 구분이 필요한 지점(`ToolAuthException` 등 커넥터 내부)만 §2.11 에 별도로 둔다.

### 2.4 `kr.co.axlink.common.web` (4)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `PageResponse<T>` | record DTO | API §1.3 목록 봉투 | `static <T> PageResponse<T> of(List<T> content, PageQuery q, long total)` |
| `PageQuery` | record DTO | `(int page, int size, List<String> sort)`. `@Min/@Max` 검증 | `int offset()`, `int limit()` |
| `SortSpec` | 값 객체 | 엔드포인트별 정렬 화이트리스트 해석. 화이트리스트 밖이면 `VALIDATION_FAILED` | `static SortSpec parse(List<String> raw, Map<String,String> whitelist, String defaultClause)`<br>`String toOrderByClause()` |
| `UpdatedAtRule` | 문서화 상수 | C-1 대가 처리: 모든 UPDATE 문에 `updated_at = now()` 를 넣는다는 규칙의 단일 상수 (`SET_UPDATED_AT = ", updated_at = now()"`) | — |

`SortSpec` 이 반환하는 `ORDER BY` 절은 화이트리스트 맵의 **값**(컬럼식)만으로 조립되며 사용자 입력 문자열이 SQL 에 들어가지 않는다.

### 2.5 `kr.co.axlink.common.crypto` (2)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `CryptoProperties` | record Config | `@ConfigurationProperties("axlink.crypto")` — `masterKey`(Base64 32B) | — |
| `SecretCipher` | Component | AES-256-GCM. 12B random IV, 출력 `Base64(IV‖ciphertext‖tag)` | `String encrypt(String plain)`<br>`String decrypt(String encoded)`<br>`static String hint(String plain)` → `"****" + 마지막 4자` |

### 2.6 `kr.co.axlink.common.json` (1)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `JsonCodec` | Component | jsonb ↔ record 단일 변환 지점. 역직렬화 실패 = 검증 실패 | `<T> T read(String json, Class<T> type)`<br>`String write(Object value)`<br>`PGobject toJsonb(Object value)`<br>`JsonNode tree(String json)` |

`ObjectMapper` 는 `FAIL_ON_UNKNOWN_PROPERTIES = true` 로 구성한다 — jsonb 스키마의 `additionalProperties: false` 를 이 설정 하나가 강제한다.

### 2.7 `kr.co.axlink.common.support` (3)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `Backoff` | 유틸 | 지수 백오프 + ±20% 지터. 커넥터·Ollama 공용 | `static <T> T retry(BackoffPolicy p, Callable<T> op, Predicate<Exception> retryable)`<br>`record BackoffPolicy(int maxAttempts, Duration initial, Duration max)` |
| `LoggingSanitizer` | Component | 로그 문자열에서 Bearer 토큰·`auth_encrypted`·프롬프트 본문 제거 | `String sanitize(String message)` |
| `Hashes` | 유틸 | SHA-256 hex. `content_hash`·`token_hash`·`file_hash` 공용 | `static String sha256Hex(byte[])`<br>`static String sha256Hex(String)` |

### 2.8 `kr.co.axlink.auth` (web 1 / service 4 / domain 3 / repository 2 = 10 + DTO 6)

**`auth.web`**

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `AuthController` | Controller | API §2.1 6엔드포인트 | `LoginResponse login(@Valid LoginRequest)`<br>`LoginResponse refresh(@Valid RefreshTokenRequest)`<br>`void logout(@Valid RefreshTokenRequest)`<br>`MeResponse me(@AuthenticationPrincipal AuthPrincipal)`<br>`InvitationPreviewResponse preview(@PathVariable String token)`<br>`LoginResponse accept(@Valid AcceptInvitationRequest)` |
| DTO | record | `LoginRequest`, `RefreshTokenRequest`, `LoginResponse`, `MeResponse`, `InvitationPreviewResponse`, `AcceptInvitationRequest` | — |

**`auth.service`**

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `AuthService` | Service | 로그인·리프레시 회전·로그아웃·초대 수락 | `LoginResponse login(LoginRequest)`<br>`LoginResponse refresh(String refreshToken)`<br>`void logout(String refreshToken)`<br>`LoginResponse acceptInvitation(AcceptInvitationRequest)` |
| `JwtIssuer` | Component | Access JWT 발급·클레임 구성(API §1.2) | `String issue(AuthPrincipal p, Instant now)`<br>`Duration accessTtl()` |
| `RefreshTokenService` | Service | 원문 생성(32B random) → `token_hash` 저장, 1회용 회전, 재사용 감지 | `String issue(UUID userId, String userAgent)`<br>`UUID rotate(String rawToken, String userAgent)`<br>`void revoke(String rawToken)` |
| `MeAssembler` | Component | `MeResponse` 조립(allowedProjectIds + permissionsByProject) | `MeResponse assemble(AuthPrincipal)` |

**`auth.domain`**

| 클래스 | 종류 | 책임 |
| --- | --- | --- |
| `AuthPrincipal` | record | `(UUID userId, UUID organizationId, OrgType orgType, Role role)`. `SecurityContext` 의 principal |
| `RefreshToken` | record | `refresh_token` 행 |
| `UserInvitation` | record | `user_invitation` 행. `boolean usable(Instant now)` |

**`auth.repository`** — `RefreshTokenRepository`, `UserInvitationRepository` (Repository, `JdbcClient` 기반)

| 클래스 | 주요 메서드 |
| --- | --- |
| `RefreshTokenRepository` | `void insert(RefreshToken)` · `Optional<RefreshToken> findByTokenHash(String)` · `int revoke(UUID id, Instant at)` · `int deleteExpired(Instant before)` |
| `UserInvitationRepository` | `void insert(UserInvitation)` · `Optional<UserInvitation> findByTokenHash(String)` · `int markAccepted(UUID id, Instant at)` |

**`kr.co.axlink.auth.security`** (필터 3)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `JwtAuthenticationFilter` | Component | `OncePerRequestFilter`. Bearer 파싱 → `JwtDecoder.decode` → `AuthPrincipal` + `ROLE_*` 권한 설정 | `void doFilterInternal(HttpServletRequest, HttpServletResponse, FilterChain)` |
| `JwtProperties` | record Config | `@ConfigurationProperties("axlink.security.jwt")` — `secret`, `accessTtl`, `refreshTtl`, `issuer` | — |
| `SecurityErrorWriter` | Component | `AuthenticationEntryPoint` + `AccessDeniedHandler`. 401/403 도 `ErrorResponse` 바디로 | `void commence(...)`, `void handle(...)` |

### 2.9 `kr.co.axlink.org` (web 2 / service 3 / domain 5 / repository 2 = 12 + DTO 7)

**`org.web`** — `OrganizationController`, `UserController`

| 클래스 | 주요 메서드 |
| --- | --- |
| `OrganizationController` | `PageResponse<OrganizationResponse> list(OrgType type, String q, PageQuery, AuthPrincipal)`<br>`OrganizationResponse create(@Valid OrganizationCreateRequest)` `@PreAuthorize("hasRole('SUPER_ADMIN')")`<br>`OrganizationResponse get(UUID)` · `OrganizationResponse update(UUID, @Valid OrganizationUpdateRequest)` |
| `UserController` | `PageResponse<UserResponse> list(UUID organizationId, Role role, UserStatus status, String q, PageQuery, AuthPrincipal)`<br>`UserResponse create(@Valid UserCreateRequest)`<br>`UserResponse get(UUID)` · `UserResponse update(UUID, @Valid UserUpdateRequest)`<br>`void resendInvitation(UUID userId)` |
| DTO | `OrganizationCreateRequest/UpdateRequest/Response`, `UserCreateRequest/UpdateRequest/Response`, `AssignmentPermissions` |

**`org.service`**

| 클래스 | 주요 메서드 |
| --- | --- |
| `OrganizationService` | `PageResponse<OrganizationResponse> list(...)` · `OrganizationResponse create(...)` · `OrganizationResponse update(...)` |
| `UserService` | `PageResponse<UserResponse> list(...)` · `UserResponse create(UserCreateRequest, AuthPrincipal)` (INV-01 조직 type ↔ role 정합 검증 포함) · `UserResponse update(...)` · `void resendInvitation(UUID)` |
| `InvitationSender` | `void send(UUID userId, String rawToken)` — 1차는 메일 발송 대신 `log.info` 로 수락 URL 을 남긴다. SMTP 의존을 추가하지 않는다 |

**`org.domain`** — `OrgType`, `OrgStatus`, `Role`, `UserStatus` (enum, 데이터모델 §3.1), `AppUser`(record), `Organization`(record) → 6

**`org.repository`** — `OrganizationRepository`, `AppUserRepository`

| 클래스 | 주요 메서드 |
| --- | --- |
| `OrganizationRepository` | `UUID insert(Organization)` · `Optional<Organization> findById(UUID)` · `List<Organization> search(OrgType, String q, SortSpec, PageQuery)` · `long countSearch(...)` · `int update(...)` |
| `AppUserRepository` | `UUID insert(AppUser)` · `Optional<AppUser> findByEmailIgnoreCase(String)` · `Optional<AppUser> findById(UUID)` · `List<AppUser> search(...)` · `int updateProfile(...)` · `int updatePasswordHash(UUID, String)` · `int touchLastLogin(UUID, Instant)` |

### 2.10 `kr.co.axlink.project` (web 2 / service 5 / domain 4 / repository 2 = 13 + DTO 12)

**`project.web`**

| 클래스 | 주요 메서드 |
| --- | --- |
| `ProjectController` | `PageResponse<ProjectSummaryResponse> list(ProjectStatus, String q, PageQuery, AuthPrincipal)`<br>`ProjectDetailResponse create(@Valid ProjectCreateRequest, AuthPrincipal)` `@PreAuthorize("hasRole('CLIENT')")`<br>`ProjectDetailResponse get(UUID, AuthPrincipal)`<br>`ProjectDetailResponse update(UUID, @Valid ProjectUpdateRequest, AuthPrincipal)`<br>`ProjectClosureResponse closureCheck(UUID, AuthPrincipal)`<br>`ProjectDetailResponse close(UUID, @Valid ProjectCloseRequest, AuthPrincipal)` |
| `AssignmentController` | `List<AssignmentResponse> list(UUID projectId, AuthPrincipal)`<br>`List<AssignmentResponse> assign(UUID projectId, @Valid AssignmentCreateRequest, AuthPrincipal)`<br>`AssignmentResponse updatePermissions(UUID projectId, UUID assignmentId, @Valid AssignmentPermissionUpdateRequest, AuthPrincipal)`<br>`void revoke(UUID projectId, UUID assignmentId, AuthPrincipal)` |
| DTO | `ProjectCreateRequest/UpdateRequest/CloseRequest`, `ProjectSummaryResponse`, `ProjectDetailResponse`, `ProjectMetrics`, `ProjectClosureResponse`, `ClosureCheck`, `AssignmentCreateRequest`, `AssignmentPermissionUpdateRequest`, `AssignmentResponse`, `AssignmentPermissions`(공유) |

**`project.service`**

| 클래스 | 책임 | 주요 메서드 |
| --- | --- | --- |
| `ProjectService` | 생성(UC-03: project → work_product 22행 → 기본 대시보드 1개, 단일 트랜잭션)·조회·수정 | `ProjectDetailResponse create(ProjectCreateRequest, AuthPrincipal)`<br>`PageResponse<ProjectSummaryResponse> list(...)`<br>`ProjectDetailResponse get(UUID, AuthPrincipal)`<br>`ProjectDetailResponse update(...)` |
| `ProjectClosureService` | INV-07 종료 게이트 3종 판정과 종료 전이 | `ProjectClosureResponse check(UUID, AuthPrincipal)`<br>`ProjectDetailResponse close(UUID, ProjectCloseRequest, AuthPrincipal)` |
| `AssignmentService` | 할당·해제·권한 토글 + `entity_history` | `List<AssignmentResponse> assign(...)` · `AssignmentResponse updatePermissions(...)` · `void revoke(...)` · `List<AssignmentResponse> list(...)` |
| `ProjectAccessResolver` | **INV-02/03 단일 지점.** `@RequestScope` 캐시 | `Set<UUID> allowedProjectIds(AuthPrincipal)`<br>`Set<UUID> resolveScope(AuthPrincipal, Collection<UUID> requested)`<br>`void requireProject(AuthPrincipal, UUID)`<br>`void requirePermission(AuthPrincipal, UUID, AssignmentPermission)` |
| `ProjectWriteGuard` | INV-10. 표준 엔티티 쓰기 서비스가 공통 호출 | `void assertWritable(UUID projectId)` — `status='CLOSED'` 면 `PROJECT_CLOSED` |
| `ProjectMetricsReader` | 목록 카드 지표(현재 SI 단계·승인 n/m·열린 조치 수)를 프로젝트 배치 1쿼리로 | `Map<UUID, ProjectMetrics> metricsOf(Collection<UUID>)` |

**`project.domain`** — `ProjectStatus`, `AssignmentStatus`(enum), `Project`(record), `ProjectAssignment`(record), `AssignmentPermission`(enum: `CONFIGURE_INTEGRATION`,`UPLOAD_DOCUMENT`,`READ_DASHBOARD`) → 5

**`project.repository`**

| 클래스 | 주요 메서드 |
| --- | --- |
| `ProjectRepository` | `UUID insert(Project)` · `Optional<Project> findById(UUID)` · `List<Project> search(Collection<UUID> projectIds, ProjectStatus, String q, SortSpec, PageQuery)` · `long countSearch(...)` · `Set<UUID> findAllIds()` · `Set<UUID> findIdsByClientOrgId(UUID)` · `int update(...)` · `int close(UUID, Instant)` |
| `ProjectAssignmentRepository` | `UUID insert(ProjectAssignment)` · `Set<UUID> findProjectIdsByUserIdAndStatus(UUID, AssignmentStatus)` · `Optional<ProjectAssignment> findActive(UUID userId, UUID projectId)` · `List<ProjectAssignment> findByProjectId(UUID)` · `int updatePermissions(UUID, String permissionsJson)` · `int revoke(UUID, Instant)` |

### 2.11 `kr.co.axlink.integration` (web 3 / service 6 / domain 8 / repository 3 / port 2 / adapter 8 / mapping 3 = 33 + DTO 12)

**`integration.web`**

| 클래스 | 주요 메서드 |
| --- | --- |
| `ToolConnectionController` | `List<ToolConnectionResponse> list(UUID projectId, AuthPrincipal)`<br>`ToolConnectionResponse create(UUID projectId, @Valid ToolConnectionCreateRequest, AuthPrincipal)`<br>`ToolConnectionResponse get/update/delete(UUID connectionId, …)`<br>`ToolConnectionResponse updateStatus(UUID, @Valid ToolConnectionStatusUpdateRequest, AuthPrincipal)`<br>`ToolConnectionTestResponse testUnsaved(@Valid ToolConnectionTestRequest, AuthPrincipal)`<br>`ToolConnectionTestResponse testSaved(UUID, AuthPrincipal)`<br>`SyncJobResponse triggerSync(UUID, @Valid SyncTriggerRequest, AuthPrincipal)` |
| `MappingRuleController` | `List<MappingRuleResponse> list(UUID connectionId, AuthPrincipal)`<br>`List<MappingRuleResponse> replace(UUID connectionId, @Valid MappingRuleReplaceRequest, AuthPrincipal)` |
| `SyncJobController` | `PageResponse<SyncJobResponse> list(UUID projectId, UUID connectionId, SyncJobStatus, SyncJobKind, PageQuery, AuthPrincipal)`<br>`SyncJobResponse get(UUID, AuthPrincipal)`<br>`SyncJobResponse retry(UUID, AuthPrincipal)`<br>`SyncJobResponse cancel(UUID, AuthPrincipal)` |
| DTO | `ToolConnectionCreateRequest/UpdateRequest/StatusUpdateRequest/TestRequest/TestResponse/Response`, `ToolCredentialRequest`, `SyncTriggerRequest`, `MappingRuleResponse/ReplaceRequest/UpsertRequest`, `SyncJobResponse`, `SyncJobStats` |

**`integration.service`**

| 클래스 | 책임 | 주요 메서드 |
| --- | --- | --- |
| `ToolConnectionService` | 연결 CRUD, 인증정보 암호화 저장, 기본 매핑규칙 시드, 생성 직후 BACKFILL enqueue | `ToolConnectionResponse create(UUID projectId, ToolConnectionCreateRequest, AuthPrincipal)`<br>`ToolConnectionResponse update(...)` · `void delete(UUID, AuthPrincipal)` · `ToolConnectionResponse changeStatus(...)` |
| `ToolConnectionTestService` | INT-002. 저장 전/후 연결 검증, 도구 오류 원문 전달 | `ToolConnectionTestResponse test(ToolConnectionTestRequest, AuthPrincipal)`<br>`ToolConnectionTestResponse test(UUID connectionId, AuthPrincipal)` |
| `ToolConnectionSecretProvider` | **복호화 단일 지점** (INV-06) | `ToolCredential resolve(UUID connectionId)` |
| `SyncJobService` | 잡 enqueue·상태 전이·커서 전진·재시도·취소 | `SyncJobResponse enqueue(UUID connectionId, SyncJobKind, AuthPrincipal)`<br>`Optional<UUID> claim(UUID connectionId, SyncJobKind)` (INV-22)<br>`void finishSucceeded(UUID jobId, SyncStats, Instant cursorTo)`<br>`void finishFailed(UUID jobId, ErrorCode, String message, SyncStats)`<br>`SyncJobResponse retry(UUID jobId, AuthPrincipal)` · `SyncJobResponse cancel(UUID, AuthPrincipal)` |
| `SyncRunner` | 잡 1건의 전 과정 실행(§4.3). 트랜잭션 밖에서 페치, 안에서 적재 | `void run(UUID syncJobId)` |
| `SyncScheduler` | `@Scheduled` 폴링 진입점 | `void pollAll()` · `void purgeOldJobs()` |

**`integration.domain`** — `ToolType`, `ToolConnectionStatus`, `SyncJobKind`, `SyncJobStatus`, `MappingSourceKind`(enum) + `ToolConnection`, `SyncJob`, `RawArtifact`(record) → 8

**`integration.repository`**

| 클래스 | 주요 메서드 |
| --- | --- |
| `ToolConnectionRepository` | `UUID insert(ToolConnection)` · `Optional<ToolConnection> findById(UUID)` · `List<ToolConnection> findByProjectId(UUID)` · `List<ToolConnection> findPollable(Instant dueBefore)` · `int updateCursor(UUID, Instant lastSyncedAt, String cursor)` · `int updateStatus(UUID, ToolConnectionStatus, String lastError)` · `int updateMappingRules(UUID, String json)` · `int delete(UUID)` |
| `SyncJobRepository` | `UUID insertQueued(UUID connectionId, SyncJobKind, Instant cursorFrom, Instant cursorTo)` · `Optional<UUID> markRunning(UUID jobId)` · `int markSucceeded(...)` · `int markFailed(...)` · `int markCancelled(UUID)` · `List<SyncJob> search(Collection<UUID> projectIds, …)` · `long countSearch(...)` · `int deleteSucceededBefore(Instant)` |
| `RawArtifactRepository` | `int upsert(RawArtifact)` (반환 0 = content_hash 동일 스킵) · `Optional<String> findContentHash(UUID connectionId, String externalId)` |

**`integration.port`**

| 클래스 | 종류 | 주요 메서드 |
| --- | --- | --- |
| `ToolConnector` | interface | `ToolType tool()`<br>`ToolProbe verify(ToolConnectionSpec spec)`<br>`FetchPage fetch(ToolConnectionSpec spec, FetchCursor cursor)` |
| `ToolConnectorTypes` | record 모음 | `ToolConnectionSpec(ToolType tool, String baseUrl, String targetResource, ToolCredential credential)`<br>`ToolCredential(String username, String secret)`<br>`ToolProbe(boolean reachable, String resourceName, List<String> detectedItemTypes)`<br>`FetchCursor(Instant since, String pageToken, int page)`<br>`FetchPage(List<RawRecord> records, FetchCursor next, boolean hasMore)`<br>`RawRecord(String externalId, String objectKind, String externalUrl, JsonNode payload, Instant sourceUpdatedAt)` |

**`integration.adapter.github`** — `GitHubConnector`, `GitHubHttpClient`, `GitHubResources`, `GitHubPaging` (미구현)
**`integration.adapter.redmine`** — `RedmineConnector`, `RedmineHttpClient` (미구현)

| 클래스 | 주요 메서드 |
| --- | --- |
| `JiraConnector` | `ToolProbe verify(ToolConnectionSpec)` · `FetchPage fetch(ToolConnectionSpec, FetchCursor)` |
| `JiraHttpClient` | `JsonNode getProject(spec, key)` · `JsonNode getIssueTypes(spec, projectId)` · `JsonNode searchJql(spec, String jql, String nextPageToken, int maxResults)` |
| `JiraJql` | `static String updatedSince(String projectKey, Instant since)` |
| `JiraFields` | `static final List<String> REQUESTED` (§4.4) |
| `GitLabConnector` | 동상 |
| `GitLabHttpClient` | `JsonNode getProject(spec)` · `JsonNode listIssues/listMergeRequests/listCommits/listPipelines/listReleases(spec, Instant since, int page)` |
| `GitLabResources` | `static String encodedProjectPath(String targetResource)` |
| `GitLabPaging` | `static Optional<Integer> nextPage(HttpHeaders)` — `x-next-page` 헤더 해석 |

**커넥터 공통 예외 3** (`integration.adapter`): `ToolAuthException`, `ToolResourceNotFoundException`, `ToolUnreachableException` — 전부 `ApiException` 하위이며 `details.toolStatus`/`toolMessage` 를 담는다.

**`integration.mapping`** (3)

| 클래스 | 종류 | 주요 메서드 |
| --- | --- | --- |
| `MappingRules` | record | `(int version, List<MappingRule> rules)` + `MappingRule(MappingSourceKind sourceKind, String sourceValue, TargetEntity targetEntity, WorkProductType targetWorkProductType, Map<String,String> statusMap, boolean enabled)` |
| `MappingRuleEngine` | Component | `Optional<StandardChange> map(MappingRules rules, ToolType tool, RawRecord record, UUID projectId, UUID connectionId)` — 규칙 미매치 시 `Optional.empty()`(= unmapped, 예외 아님. INV-21) |
| `MappingRuleDefaults` | 상수 | `static MappingRules seedFor(ToolType tool, List<String> detectedItemTypes)` |

### 2.12 `kr.co.axlink.standard` (web 6 / service 8 / domain 21 / repository 9 / history 3 = 47 + DTO 20)

**`standard.web`** — 엔티티별로 컨트롤러를 쪼개지 않고 화면 단위로 6개만 둔다.

| 클래스 | 담당 엔드포인트 |
| --- | --- |
| `RequirementController` | 목록·상세·상태 전이 (API §2.8) |
| `IssueController` | 목록·상세 |
| `WorkProductController` | 22종 점검표·상세·상태 전이 |
| `RiskController` | 목록 |
| `GovernanceController` | change-requests · correction-actions · progress-records · acceptance-record (STD-003/004) |
| `TraceabilityController` | traceability · trace-links CRUD |
| `EntityHistoryController` | 감사 이력 조회 |
| DTO | `EntityStatusUpdateRequest`, `SourceRef`, `RequirementResponse`, `RequirementDetailResponse`, `IssueResponse`, `WorkProductChecklistResponse`, `WorkProductResponse`, `WorkProductDetailResponse`, `WorkProductVersionResponse`, `WorkProductStatusUpdateRequest`, `RiskResponse`, `ChangeRequestResponse`, `CorrectionActionResponse`, `TraceLinkResponse`, `TraceLinkCreateRequest`, `TraceabilityRowResponse`, `TraceCell`, `ProgressRecordResponse`, `AcceptanceRecordCreateRequest`, `AcceptanceRecordResponse`, `EntityHistoryResponse` |

**`standard.service`**

| 클래스 | 책임 | 주요 메서드 |
| --- | --- | --- |
| `StandardEntityService` | 동기화·정형화가 만든 `StandardChange` 목록의 멱등 upsert + 이력 기록 (§4.6) | `UpsertResult upsertAll(List<StandardChange> changes, String actor)`<br>`record UpsertResult(int inserted, int updated, Map<DocSourceType, Set<UUID>> changedSources)` |
| `RequirementService` | 조회·상태 전이 | `PageResponse<RequirementResponse> list(UUID projectId, …, AuthPrincipal)` · `RequirementDetailResponse get(UUID, AuthPrincipal)` · `RequirementResponse changeStatus(UUID, EntityStatusUpdateRequest, AuthPrincipal)` |
| `IssueService` | 조회 | `PageResponse<IssueResponse> list(...)` · `IssueResponse get(...)` |
| `WorkProductService` | 22행 초기화, 점검표, 버전 전환, 상태 전이 | `void initializeChecklist(UUID projectId)`<br>`WorkProductChecklistResponse checklist(UUID projectId, AuthPrincipal)`<br>`WorkProductDetailResponse get(UUID, AuthPrincipal)`<br>`WorkProductResponse changeStatus(UUID, WorkProductStatusUpdateRequest, AuthPrincipal)`<br>`UUID upsertNewVersion(UUID projectId, WorkProductType, String version, …)` |
| `RiskService` | 조회 + `severity` 계산 저장 | `PageResponse<RiskResponse> list(...)` · `static RiskLevel severityOf(RiskLevel probability, RiskLevel impact)` |
| `GovernanceService` | change_request·correction_action·progress_record·acceptance_record | `PageResponse<ChangeRequestResponse> listChangeRequests(...)` · `ChangeRequestResponse changeStatus(...)` · `PageResponse<CorrectionActionResponse> listCorrections(...)` · `CorrectionActionResponse changeCorrectionStatus(...)` · `PageResponse<ProgressRecordResponse> listProgress(...)` · `AcceptanceRecordResponse createAcceptance(...)` · `Optional<AcceptanceRecordResponse> findAcceptance(...)` |
| `TraceLinkService` | INV-13 실재 검증 후 링크 생성, 자동 링크 생성 | `TraceLinkResponse createManual(UUID projectId, TraceLinkCreateRequest, AuthPrincipal)`<br>`int createAuto(UUID projectId, List<TraceLinkDraft> drafts)`<br>`void delete(UUID, AuthPrincipal)` |
| `TraceabilityService` | STD-002 추적표 행 조립(끊김 판정) | `PageResponse<TraceabilityRowResponse> rows(UUID projectId, PageQuery, AuthPrincipal)` |
| `CorrectionOverdueScheduler` | 일 1회 `OPEN` + `due_date < current_date` → `OVERDUE` 승격, 22행 누락 보충 (INV-12 정합 배치) | `void sweepOverdue()` · `void backfillMissingChecklistRows()` |

**`standard.domain`** (21) — enum 17종: `Iso29110Activity`, `SourceKind`, `WorkProductType`(22값), `WorkProductStatus`, `RequirementStatus`, `RequirementPriority`, `IssueStatus`, `IssueSeverity`, `RiskStatus`, `RiskLevel`, `ChangeRequestStatus`, `CorrectionStatus`, `AcceptanceStatus`, `TraceLinkKind`, `TraceLinkOrigin`, `TraceLinkStatus`, `TraceEntityType`, `CodeChangeKind`, `CodeChangeState`, `HistoryEntityType` (20) + `StandardChange`(record: 대상 엔티티·필드맵·원천 공통 컬럼).

상태 전이 규칙(INV-15)은 각 상태 enum 안에 둔다: `boolean canTransitionTo(Self next)`. 별도 `StateMachine` 클래스를 만들지 않는다.

**`standard.repository`** (9) — `RequirementRepository`, `IssueRepository`, `WorkProductRepository`, `RiskRepository`, `CodeChangeRepository`, `TraceLinkRepository`, `ChangeRequestRepository`, `CorrectionActionRepository`, `GovernanceRepository`(progress_record·meeting_record·acceptance_record 3테이블 공용)

공통 메서드 형태(6개 원천 연동 테이블):

```java
int upsertFromTool(UUID projectId, UUID connectionId, String externalId, String externalUrl, Map<String,Object> fields);
List<XxxRow> search(Collection<UUID> projectIds, /* 필터 */, SortSpec sort, PageQuery page);
long countSearch(Collection<UUID> projectIds, /* 필터 */);
Optional<XxxRow> findById(UUID id);
int updateStatus(UUID id, Enum<?> next, Instant now);
```

**`standard.history`** (3)

| 클래스 | 종류 | 주요 메서드 |
| --- | --- | --- |
| `EntityHistoryRecorder` | Component | `void record(HistoryEntityType, UUID entityId, UUID projectId, String field, String from, String to, String actor)`<br>`void recordDiff(HistoryEntityType, UUID, UUID, Map<String,String> before, Map<String,String> after, String actor)` — 실제로 바뀐 필드만 append |
| `EntityHistoryRepository` | Repository | `void insertAll(List<EntityHistory>)` · `List<EntityHistory> search(HistoryEntityType, UUID entityId, Collection<UUID> projectIds, PageQuery)` |
| `EntityHistory` | record | 행 표현 |

### 2.13 `kr.co.axlink.document` (web 1 / service 5 / domain 4 / repository 2 / extract 4 = 16 + DTO 6)

**`document.web`** — `DocumentController` (API §2.13 8엔드포인트)

| 메서드 |
| --- |
| `PageResponse<DocumentUploadResponse> list(UUID projectId, DocumentUploadStatus, PageQuery, AuthPrincipal)`<br>`DocumentUploadResponse upload(UUID projectId, MultipartFile file, AuthPrincipal)` → 202<br>`DocumentUploadResponse get(UUID documentId, AuthPrincipal)`<br>`StructuringDraftResponse draft(UUID documentId, AuthPrincipal)`<br>`StructuringConfirmResponse confirm(UUID, @Valid StructuringConfirmRequest, AuthPrincipal)`<br>`void reject(UUID, AuthPrincipal)` · `void delete(UUID, AuthPrincipal)`<br>`ResponseEntity<Resource> content(UUID, AuthPrincipal)` |
| DTO | `DocumentUploadResponse`, `StructuringDraftResponse`, `DraftRequirement`, `StructuringConfirmRequest`, `StructuringConfirmResponse`, `DraftJson`(jsonb 매핑 record) |

**`document.service`**

| 클래스 | 책임 | 주요 메서드 |
| --- | --- | --- |
| `DocumentUploadService` | 확장자·MIME·크기·해시 검증, 파일 저장, 202 반환 후 파이프라인 기동 | `DocumentUploadResponse upload(UUID projectId, MultipartFile, AuthPrincipal)`<br>`DocumentUploadResponse get(UUID, AuthPrincipal)` · `void delete(UUID, AuthPrincipal)` |
| `DocumentPipeline` | `documentExecutor` 위에서 추출 → 정형화 → 상태 전이. 실패는 `status=FAILED` + `error` | `void process(UUID documentUploadId)` |
| `StructuringService` | `deepseek-v4-pro:cloud` tool calling → 22종 enum 검증 → `structuring_draft` 저장 | `void structure(UUID documentUploadId, String text, Integer pageCount)`<br>`StructuringDraftResponse draft(UUID documentId, AuthPrincipal)` |
| `StructuringConfirmService` | **INV-33 유일 쓰기 지점**: work_product upsert + requirement insert + 색인 | `StructuringConfirmResponse confirm(UUID documentId, StructuringConfirmRequest, AuthPrincipal)`<br>`void reject(UUID documentId, AuthPrincipal)` |
| `DocumentStorage` | `axlink.storage.root` 하위 `{projectId}/{uuid}.{ext}` 저장·읽기·삭제 | `String store(UUID projectId, String ext, InputStream)` · `Resource load(String storedPath)` · `void delete(String storedPath)` |

**`document.domain`** — `UploadExt`, `DocumentUploadStatus`, `StructuringDraftStatus`(enum), `DocumentUpload`, `StructuringDraft`(record) → 5

**`document.repository`** — `DocumentUploadRepository`, `StructuringDraftRepository`

**`document.extract`** (4)

| 클래스 | 종류 | 주요 메서드 |
| --- | --- | --- |
| `TextExtractor` | interface | `boolean supports(UploadExt)` · `ExtractedText extract(Path file)` |
| `TikaTextExtractor` | Adapter | PDF·DOCX·XLSX. `AutoDetectParser` + `BodyContentHandler(-1)`. `pageNo` 는 PDF 만 `xmpTPg:NPages` 로 채운다 |
| `HwpTextExtractor` | Adapter | HWP(hwplib)·HWPX(hwpxlib) |
| `ExtractedText` | record | `(String text, Integer pageCount)` |

### 2.14 `kr.co.axlink.semantic` (web 1 / service 6 / domain 8 / repository 1 = 16 + DTO 5)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `SemanticCatalogController` | Controller | API §2.11 | `SemanticCatalogResponse catalog()` · `SemanticMeasureResponse measure(String key)` |
| `CatalogRegistry` | Component | 기동 시 3테이블 전량 로드 → 불변 맵. 카탈로그는 Flyway 로만 바뀌므로 런타임 갱신 경로를 두지 않는다 | `void load()` `@EventListener(ApplicationReadyEvent)`<br>`Optional<MeasureDef> measure(String key)`<br>`Optional<DimensionDef> dimension(String key)`<br>`Optional<FilterDef> filter(String field, FilterOp op)`<br>`List<MeasureDef> activeMeasures()` |
| `WidgetSpecValidator` | Component | V1~V7 (API §5.1) 순서 고정 검증 | `ValidatedSpec validate(WidgetSpec spec, Set<UUID> allowedProjectIds)` |
| `SemanticQueryBuilder` | Component | §7.1 골격 SQL 조립. **`allowedProjectIds` 필수 인자** | `BuiltQuery build(ValidatedSpec spec, Set<UUID> allowedProjectIds)`<br>`record BuiltQuery(String sql, Map<String,Object> params, List<WidgetColumn> columns)` |
| `SemanticQueryExecutor` | Service | 실행 + 행 → `WidgetDataResponse` 변환 | `WidgetDataResponse run(WidgetSpec spec, Set<UUID> allowedProjectIds, WidgetDataRequest override)`<br>`AggregateContext runForRag(String measureKey, List<String> dimensions, List<WidgetFilter> filters, Set<UUID> allowedProjectIds)` |
| `WidgetDataAssembler` | Component | 템플릿별 컬럼·total·previousTotal 구성 | `WidgetDataResponse assemble(MeasureDef, List<Map<String,Object>> rows, ValidatedSpec, Set<UUID> applied)` |
| `FilterBinder` | Component | `op` 별 SQL 조각 + 바인딩(§5.4) | `Fragment bind(FilterDef def, WidgetFilter value, String timeColumn, int index)` |
| `TimeColumns` | 상수 | `base_table` → `<TIME_COL>` 매핑(데이터모델 §7.3 표) | `static String of(String baseTable)` |
| `SemanticCatalogRepository` | Repository | 3테이블 조회 전용(쓰기 메서드 없음) | `List<MeasureDef> findActiveMeasures()` · `List<DimensionDef> findActiveDimensions()` · `List<FilterDef> findActiveFilters()` |
| `semantic.domain` | record/enum | `MeasureDef`, `DimensionDef`, `FilterDef`, `ValidatedSpec`, `AggregateContext`, `CatalogStatus`, `MeasureValueType`, `DimensionValueType`, `FilterOp`, `FilterValueType` (10) | — |
| DTO | record | `SemanticCatalogResponse`, `SemanticMeasureResponse`, `SemanticDimensionResponse`, `SemanticFilterResponse`, `WidgetColumn` | — |

### 2.15 `kr.co.axlink.dashboard` (web 2 / service 4 / domain 3 / repository 2 = 11 + DTO 12)

| 클래스 | 종류 | 주요 메서드 |
| --- | --- | --- |
| `DashboardController` | Controller | `List<DashboardSummaryResponse> list(UUID projectId, AuthPrincipal)` · `DashboardDetailResponse create/get/update(...)` · `void delete(UUID, AuthPrincipal)` · `DashboardDetailResponse replaceLayout(UUID, @Valid DashboardLayoutUpdateRequest, AuthPrincipal)` |
| `WidgetController` | Controller | `WidgetGenerateResponse generate(@Valid WidgetGenerateRequest, AuthPrincipal)` · `WidgetDataResponse preview(@Valid WidgetPreviewRequest, AuthPrincipal)` · `WidgetResponse create(UUID dashboardId, @Valid WidgetCreateRequest, AuthPrincipal)` · `WidgetResponse update(UUID, @Valid WidgetUpdateRequest, AuthPrincipal)` · `void delete(UUID, AuthPrincipal)` · `WidgetDataResponse data(UUID widgetId, @Valid WidgetDataRequest, AuthPrincipal)` |
| `DashboardService` | Service | `DashboardDetailResponse create(...)` · `void createDefault(UUID projectId, UUID ownerUserId)` · `DashboardDetailResponse get(...)` · `DashboardDetailResponse replaceLayout(...)` (layout `i` ↔ ACTIVE widget id 정합 검증 후 저장) |
| `WidgetService` | Service | `WidgetResponse create(...)` · `WidgetResponse update(...)` · `void delete(...)` · `WidgetDataResponse data(UUID widgetId, WidgetDataRequest, AuthPrincipal)` |
| `WidgetGenerationService` | Service | `glm-5.2:cloud` `build_widget_spec` tool calling → 검증 → 미리보기 | `WidgetGenerateResponse generate(WidgetGenerateRequest, AuthPrincipal)` |
| `WidgetToolSchemaFactory` | Component | 카탈로그에서 tool `parameters` enum 을 **런타임 생성**(하드코딩 금지) | `ToolSchema buildWidgetSpecSchema()` · `ToolSchema classifyQuerySchema()` · `ToolSchema suggestQuestionsSchema()` |
| `dashboard.domain` | enum/record | `WidgetTemplate`(8값), `WidgetStatus`, `DashboardStatus`, `Dashboard`, `Widget` (5) |
| `dashboard.repository` | Repository | `DashboardRepository`(layout jsonb 손매퍼), `WidgetRepository` |
| DTO | record | `DashboardCreateRequest/UpdateRequest/SummaryResponse/DetailResponse`, `DashboardLayout`, `GridItem`, `DashboardLayoutUpdateRequest`, `WidgetResponse/CreateRequest/UpdateRequest`, `WidgetSpec`, `WidgetQuery`, `WidgetFilter`, `WidgetOptions`, `WidgetThreshold`, `WidgetGenerateRequest/Response`, `WidgetGenerationRejection`, `WidgetPreviewRequest`, `WidgetDataRequest/Response`, `WidgetRow` |

### 2.16 `kr.co.axlink.rag` (web 2 / service 8 / domain 6 / repository 3 = 19 + DTO 9)

| 클래스 | 종류 | 책임 | 주요 메서드 |
| --- | --- | --- | --- |
| `ConversationController` | Controller | API §2.12 대화 CRUD + 추천 질문 | `PageResponse<ConversationResponse> list(...)` · `ConversationResponse create/get/update(...)` · `void delete(...)` · `List<MessageResponse> messages(UUID, AuthPrincipal)` · `void feedback(UUID messageId, @Valid MessageFeedbackRequest, AuthPrincipal)` · `SuggestedQuestionsResponse suggestions(List<UUID> projectIds, AuthPrincipal)` |
| `AskController` | Controller | SSE 엔드포인트 단독 | `SseEmitter ask(UUID conversationId, @Valid AskRequest, AuthPrincipal)` |
| `ConversationService` | Service | 대화·메시지 CRUD, 피드백 | `…` |
| `RagOrchestrator` | Service | 라우팅 → 집계 → 검색 → 융합 → 합성 → 저장의 순서 소유 | `void ask(AskContext ctx, SseSink sink)` |
| `QueryRouter` | Component | `classify_query` tool calling. 실패 시 `DOCUMENT` 로 폴백 | `QueryRouting route(String question, List<Message> history)` |
| `HybridSearchService` | Service | 벡터·어휘 두 쿼리 실행 + RRF 융합 | `RetrievalSet search(float[] queryVector, String queryText, Set<UUID> projectIds, int perListLimit, int finalLimit)` |
| `ContextAssembler` | Component | top-8 청크 + 집계 결과 → 프롬프트 컨텍스트 문자열(청크당 1KB 상한) | `String assemble(RetrievalSet, AggregateContext, QueryRouting)` |
| `AnswerPostProcessor` | Component | INV-31/32. 각주 스캔 → 미대응 제거 → `message_source` 목록 산출 | `ProcessedAnswer process(String rawText, RetrievalSet set)` |
| `ChunkingService` | Component | 표제 계층 기반 분할(§6.2) | `List<ChunkDraft> chunk(DocSourceType, String title, String body, Map<String,Object> meta)` |
| `IndexingService` | Service | 재색인 단위 delete + insert, 배치 임베딩 | `int reindex(DocSourceType type, UUID sourceId, UUID projectId)`<br>`int reindexAll(Map<DocSourceType, Set<UUID>> changed)`<br>`void deleteBySource(DocSourceType, UUID)` |
| `SuggestionService` | Service | QNA-005 추천 질문 4개 | `SuggestedQuestionsResponse suggest(Set<UUID> projectIds)` |
| `SseSink` | Component | `SseEmitter` 래퍼. 이벤트 순서·하트비트·종료 처리 단일 지점 | `void start(SseStartEvent)` · `void delta(String)` · `void sources(List<MessageSourceResponse>)` · `void done(SseDoneEvent)` · `void error(ErrorResponse)` · `boolean isClosed()` |
| `rag.domain` | enum/record | `DocSourceType`, `ConversationStatus`, `MessageRole`, `MessageStatus`, `MessageFeedback`, `QueryRouteType` (enum 6) + `DocChunk`, `RetrievalSet`, `ScoredChunk`, `ChunkDraft`, `AskContext`, `ProcessedAnswer` (record 6) |
| `rag.repository` | Repository | `DocChunkRepository`(vector 손매퍼), `HybridSearchRepository`, `ConversationRepository`(message·message_source 포함) |
| DTO | record | `ConversationCreateRequest/UpdateRequest/Response`, `AskRequest`, `MessageResponse`, `QueryRouting`, `MessageSourceResponse`, `MessageFeedbackRequest`, `SuggestedQuestionsResponse`, `SseStartEvent/DeltaEvent/SourcesEvent/DoneEvent` |

### 2.17 `kr.co.axlink.ai` (port 9 / ollama 4 / fake 2 / prompt 2 = 17)

**`ai.port`** (9)

| 클래스 | 종류 | 시그니처 |
| --- | --- | --- |
| `LlmPort` | interface | `LlmResponse complete(LlmRequest)`<br>`void stream(LlmRequest, Consumer<LlmDelta>)`<br>`ToolInvocation callTool(ToolRequest)` |
| `EmbeddingPort` | interface | `List<float[]> embed(List<String> texts)`<br>`int dimension()` |
| `LlmRequest` | record | `(String model, List<LlmMessage> messages, Double temperature, Integer maxTokens, boolean think)` |
| `LlmMessage` | record | `(LlmRole role, String content)` |
| `LlmRole` | enum | `SYSTEM`,`USER`,`ASSISTANT`,`TOOL` |
| `LlmResponse` | record | `(String text, String model, int promptTokens, int completionTokens)` |
| `LlmDelta` | record | `(String text, boolean done)` |
| `ToolRequest` / `ToolSchema` / `ToolInvocation` | record | `ToolRequest(LlmRequest base, ToolSchema tool)`<br>`ToolSchema(String name, String description, Map<String,Object> parameters)`<br>`ToolInvocation(String toolName, JsonNode arguments, String rawText)` |
| `LlmModels` | 상수 | `SYNTHESIS`,`STRUCTURING`,`EMBEDDING` — 값은 `AiProperties` 에서 주입 |

**`stream` 을 `Flow.Publisher` 가 아니라 `Consumer<LlmDelta>` 로 확정하는 이유**: 소비자가 `SseSink` 하나뿐이고, 취소는 `SseSink.isClosed()` 확인 후 `HttpClient` 스트림을 닫는 것으로 끝난다. `Flow` 를 쓰면 백프레셔 구현체를 직접 써야 하는데 실제로 흘려보낼 곳이 SSE 한 곳이다.

**`ai.adapter.ollama`** (4)

| 클래스 | 종류 | 주요 메서드 |
| --- | --- | --- |
| `OllamaLlmAdapter` | Adapter | `LlmPort` 구현. `POST /api/chat`. **요청 body 빌더에 `format` 키를 넣는 코드가 존재하지 않는다** (INV-34) |
| `OllamaEmbeddingAdapter` | Adapter | `EmbeddingPort` 구현. `POST /api/embed` `{model, input:[...]}`, 배치 32 |
| `OllamaWire` | record 모음 | 요청·응답 JSON 매핑 record (`ChatRequest`, `ChatMessage`, `ToolDef`, `ChatChunk`, `EmbedRequest`, `EmbedResponse`) |
| `AiProperties` | record Config | `@ConfigurationProperties("axlink.ai")` |

**`ai.adapter.fake`** (2) — `FakeLlmAdapter`, `FakeEmbeddingAdapter` (아키텍처 §3.2 결정성 규칙 그대로)

**`ai.prompt`** (2) — `Prompts`(system 프롬프트 상수 4종), `ToolNames`(`build_widget_spec`,`classify_query`,`suggest_questions`,`structure_work_product`)

### 2.18 패키지·클래스 집계

| 구분 | 수 |
| --- | --- |
| 패키지 | **53** |
| Controller | 20 |
| Service / Component | 78 |
| Repository | 25 |
| Config / Properties | 12 |
| Port(interface) | 4 |
| Adapter | 12 |
| domain record·enum | 92 |
| record DTO | 106 |
| **클래스 합계** | **349** |

---

## 3. 인증·인가 물리 설계

### 3.1 필터체인

```
SecurityFilterChain
  csrf().disable()                                  ← Bearer 토큰은 CSRF 대상이 아니다
  cors(dev 프로파일에서만 http://localhost:5173)
  sessionManagement(SessionCreationPolicy.STATELESS)
  httpBasic().disable()  formLogin().disable()  logout().disable()
  exceptionHandling(entryPoint = SecurityErrorWriter, accessDeniedHandler = SecurityErrorWriter)
  authorizeHttpRequests
    permitAll : POST /api/auth/login, POST /api/auth/refresh,
                POST /api/auth/invitations/accept, GET /api/auth/invitations/{token},
                GET /actuator/health
    그 외 /api/**  : authenticated()
    그 외 전체      : denyAll()
  addFilterBefore(JwtAuthenticationFilter, UsernamePasswordAuthenticationFilter)
```

| 항목 | 확정 |
| --- | --- |
| 세션 vs 토큰 | **토큰(Bearer JWT)**. API §1.2 확정값. 서버 세션 저장소가 없다 |
| Access JWT | HS256. `NimbusJwtEncoder(ImmutableSecret(axlink.security.jwt.secret))`. TTL 30분 |
| Refresh | 32바이트 random → Base64URL 원문을 응답에만 싣고, DB 에는 `Hashes.sha256Hex(raw)` 만 저장. 1회용 회전(구 행 `revoked_at` 설정 + 새 행 insert). **이미 `revoked_at` 이 찍힌 토큰이 다시 오면 재사용 공격으로 보고 해당 사용자의 전 refresh 행을 폐기하고 `AUTH_TOKEN_INVALID`** |
| 비밀번호 인코더 | `BCryptPasswordEncoder(10)`. `password_hash varchar(72)` 와 정확히 맞는다 |
| 익명 4경로 | 위 permitAll 목록 외에는 만들지 않는다 |

### 3.2 현재 사용자 해석

`JwtAuthenticationFilter` 가 `UsernamePasswordAuthenticationToken(authPrincipal, null, List.of(new SimpleGrantedAuthority("ROLE_" + role)))` 를 `SecurityContext` 에 넣는다. 컨트롤러는 `@AuthenticationPrincipal AuthPrincipal principal` 로 받는다 — **커스텀 `HandlerMethodArgumentResolver` 를 만들지 않는다**. Spring Security 가 제공하는 리졸버가 principal 객체를 그대로 주입한다.

JWT 클레임은 API §1.2 그대로이며 **`allowedProjectIds` 를 넣지 않는다.**

### 3.3 `allowedProjectIds` 산출

`ProjectAccessResolver` 를 `@Component @RequestScope` 로 둔다. 인스턴스 필드에 `Set<UUID> cached` 를 갖고 요청 내 첫 호출에서만 DB 를 친다.

| 역할 | 쿼리 |
| --- | --- |
| `SUPER_ADMIN` | `select id from project` |
| `CLIENT` | `select id from project where client_org_id = :orgId` |
| `CONTRACTOR` | `select project_id from project_assignment where user_id = :userId and status = 'ACTIVE'` (`ix_project_assignment__user_status` 사용) |

요청 스코프보다 긴 캐시를 두지 않는다 — 할당 해제가 다음 요청부터 즉시 반영되어야 한다(INV-02).

### 3.4 인가 적용 방식 — **`@PreAuthorize`(역할) + 명시적 가드(프로젝트·세부권한) 혼합으로 확정**

| 게이트 | 방식 | 위치 |
| --- | --- | --- |
| G2 역할 | `@PreAuthorize("hasRole('CLIENT')")` / `hasAnyRole(...)` | **컨트롤러 메서드에만** |
| G3 프로젝트 범위 | `projectAccessResolver.requireProject(p, projectId)` / `resolveScope(p, requested)` | **서비스 메서드 첫 줄** |
| G4 세부 권한 | `projectAccessResolver.requirePermission(p, projectId, CONFIGURE_INTEGRATION)` | 서비스 메서드 |

**하나로 통일하지 않는 근거**: 역할 게이트는 PRD §3.2 매트릭스와 1:1인 정적 규칙이라 애노테이션이 문서 그 자체가 된다. 반면 G3 는 **판정 결과(`Set<UUID>`)를 서비스가 그대로 쿼리 인자로 써야 한다.** 이를 SpEL(`@PreAuthorize("@projectAccessResolver.can(...)")`)로 처리하면 판정 1회 + 서비스에서 목록 산출 1회로 같은 조회를 두 번 하게 되고, 실패 경로가 `AccessDeniedException` 하나로 뭉개져 `PROJECT_ACCESS_DENIED` 와 `ASSIGNMENT_PERMISSION_DENIED` 를 구분할 수 없다. 반대로 역할까지 전부 명시적 가드로 내리면 컨트롤러마다 `if (p.role() != CLIENT) throw ...` 가 20번 반복된다.

경계 규칙 3가지:
1. `@PreAuthorize` 는 **컨트롤러에만** 붙인다. 서비스에 붙이면 스케줄러·파이프라인 호출 시 `SecurityContext` 가 비어 실패한다.
2. `@PreAuthorize` 안에 SpEL 빈 호출(`@bean.method(...)`)을 쓰지 않는다.
3. 단건 조회는 `requireProject` 실패 시 **404**(`RESOURCE_NOT_FOUND`)로 변환한다(존재 노출 방지, API §1.5). 프로젝트 리소스 자체(`/api/projects/{id}`)만 403.

---

## 4. 동기화 엔진 물리 설계

### 4.1 스케줄러 구성

| 항목 | 값 |
| --- | --- |
| 진입점 | `SyncScheduler.pollAll()` — `@Scheduled(fixedDelayString = "${axlink.sync.poll-interval-ms}")` (기본 900000ms = 15분), `initialDelay` 60000ms |
| 대상 조회 | `ToolConnectionRepository.findPollable(now - pollInterval)` → `select tc.* from tool_connection tc join project p on p.id = tc.project_id where tc.status = 'ACTIVE' and p.status <> 'CLOSED' and (tc.last_synced_at is null or tc.last_synced_at < :dueBefore) order by tc.last_synced_at nulls first` |
| 실행 | 연결마다 `syncExecutor` (코어 2, 큐 32) 에 제출. 스케줄러 스레드는 제출만 한다 |
| 실패 격리 | 연결 1건의 예외는 그 연결의 `sync_job` 에만 기록되고 루프는 계속된다. `pollAll()` 자체는 예외를 던지지 않는다 (`@Scheduled` 메서드가 예외를 던지면 스케줄이 죽는다) |
| 보관 배치 | `SyncScheduler.purgeOldJobs()` — `@Scheduled(cron = "0 20 3 * * *")`, `delete from sync_job where status='SUCCEEDED' and finished_at < now() - interval '90 days'` |
| 시정조치 배치 | `CorrectionOverdueScheduler.sweepOverdue()` — `@Scheduled(cron = "0 10 3 * * *")` |

### 4.2 `sync_job` 상태 전이와 중복 실행 방지

```
enqueue           → QUEUED
QUEUED  --claim-->  RUNNING   (uq_sync_job__running 위반 시 claim 실패 → 이번 회차 스킵)
RUNNING --ok----->  SUCCEEDED (커서 전진)
RUNNING --fail--->  FAILED    (커서 유지)
QUEUED|RUNNING --cancel--> CANCELLED
FAILED  --retry-->  (신규 QUEUED 행, retry_of_job_id = 원본)
```

`claim` SQL:

```sql
update sync_job
   set status = 'RUNNING', started_at = now(), updated_at = now()
 where id = :jobId and status = 'QUEUED'
returning id;
```

`uq_sync_job__running (tool_connection_id) where status = 'RUNNING'` 위반은 `DuplicateKeyException` 으로 올라오며, `SyncJobService.claim` 은 이를 잡아 `Optional.empty()` 를 반환한다(잡 행은 `QUEUED` 로 남아 다음 회차에 다시 시도된다).

**`pg_try_advisory_lock` 을 쓰지 않는다** — 아키텍처 §5.3 은 어드바이저리 락과 부분 유니크 인덱스를 함께 적었으나, 부분 유니크 인덱스 하나가 동일한 상호배제를 DB 트랜잭션 안에서 이미 보장한다. 어드바이저리 락은 세션 수명 관리(획득 커넥션과 해제 커넥션이 같아야 함)를 `JdbcClient` 위에 직접 얹어야 하고, 그 대가로 얻는 것이 없다. 다중 인스턴스로 갈 때도 유니크 인덱스는 그대로 동작한다.

### 4.3 잡 1건의 실행 순서 (`SyncRunner.run`)

| # | 단계 | 트랜잭션 |
| --- | --- | --- |
| 1 | `claim(jobId)` → 실패 시 즉시 종료 | T1 |
| 2 | `ToolConnectionSecretProvider.resolve()` 로 복호화 | 없음 |
| 3 | `cursorFrom` 결정: `BACKFILL` → `1970-01-01T00:00:00Z`, `POLL` → `last_synced_at - 60s`(null 이면 `1970-01-01`). `cursorTo = now()` | 없음 |
| 4 | `connector.fetch(spec, cursor)` 반복 (페이지네이션 + 백오프) | **밖** |
| 5 | 페이지마다 `raw_artifact` upsert. `content_hash` 동일 행은 `stats.unchangedSkipped++` 후 이후 단계 제외 (INV-20) | 페이지당 T |
| 6 | `MappingRuleEngine.map(...)` → `List<StandardChange>` + `unmapped` 집계 (INV-21) | 없음 |
| 7 | `StandardEntityService.upsertAll(changes, "system:sync:{connectionId}")` — upsert + `entity_history` append | **1 트랜잭션** |
| 8 | `TraceLinkService.createAuto(...)` — MR·커밋 제목의 이슈 키 정규식 매칭 | T |
| 9 | `IndexingService.reindexAll(changedSources)` — 소스 1건당 delete+insert 1 트랜잭션 | 소스당 T |
| 10 | 성공: `finishSucceeded(jobId, stats, cursorTo)` → 같은 트랜잭션에서 `tool_connection.last_synced_at = cursorTo` (INV-23)<br>실패: `finishFailed(jobId, errorCode, message, stats)` → 커서 미변경 | T |

4~9 중 어디서 실패해도 커서가 전진하지 않으므로 다음 회차가 같은 구간을 다시 처리한다. 5·7 의 upsert 가 멱등이라 재처리가 안전하다.

### 4.4 Jira 클라이언트

| 항목 | 값 |
| --- | --- |
| 인증 | `Authorization: Basic base64(email + ":" + apiToken)` — `ToolCredential(username=email, secret=apiToken)` |
| 연결 테스트 | `GET {baseUrl}/rest/api/3/project/{projectKey}` → 200 이면 `GET /rest/api/3/issuetype/project?projectId={id}` 로 `detectedItemTypes` 수집 |
| 증분 페치 | `POST {baseUrl}/rest/api/3/search/jql` |
| 요청 body | `{"jql": "project = \"{KEY}\" AND updated >= \"{yyyy/MM/dd HH:mm}\" ORDER BY updated ASC", "maxResults": 100, "nextPageToken": "{token|null}", "fields": [...]}` |
| `fields` | `summary, description, issuetype, status, priority, assignee, created, updated, resolutiondate, labels, parent, fixVersions` |
| 페이지네이션 | 응답 `nextPageToken` 이 있으면 다음 페이지. `isLast=true` 또는 토큰 없음 → 종료. **`startAt`/`total` 기반 페이징을 쓰지 않는다** (해당 엔드포인트는 제공하지 않는다) |
| 시각 포맷 | JQL 은 `yyyy/MM/dd HH:mm` (분 단위). `cursorFrom` 을 이 포맷으로 절삭하므로 60초 겹침 정책과 자연히 맞는다 |
| `objectKind` | `JIRA_ISSUE` |
| `externalId` | 이슈 `key` (`PROJ-123`) — `issue.issue_key` 매칭에 그대로 쓰인다 |
| `externalUrl` | `{baseUrl}/browse/{key}` |

### 4.5 GitLab 클라이언트

| 항목 | 값 |
| --- | --- |
| 인증 | `PRIVATE-TOKEN: {accessToken}` |
| 프로젝트 식별 | `targetResource`(그룹/프로젝트 경로 또는 숫자 ID) → `URLEncoder.encode(path, UTF_8)` |
| 연결 테스트 | `GET {baseUrl}/api/v4/projects/{encoded}` |
| 페치 대상 5종 | `objectKind` / 엔드포인트 / 증분 파라미터 |
| | `GITLAB_ISSUE` — `GET /projects/{id}/issues?updated_after={ISO}&order_by=updated_at&sort=asc&per_page=100&page=N` |
| | `GITLAB_MERGE_REQUEST` — `GET /projects/{id}/merge_requests?updated_after={ISO}&order_by=updated_at&sort=asc&per_page=100&page=N` |
| | `GITLAB_COMMIT` — `GET /projects/{id}/repository/commits?since={ISO}&per_page=100&page=N` |
| | `GITLAB_PIPELINE` — `GET /projects/{id}/pipelines?updated_after={ISO}&order_by=updated_at&sort=asc&per_page=100&page=N` |
| | `GITLAB_RELEASE` — `GET /projects/{id}/releases?per_page=100&page=N` (증분 파라미터 없음 → `released_at` 을 클라이언트에서 `since` 로 걸러낸다) |
| 페이지네이션 | 응답 헤더 `x-next-page`. 값이 비어 있으면 종료 |
| `externalId` | `{objectKind}:{iid 또는 sha 또는 id}` — 종류가 섞이므로 접두를 붙여 `(tool_connection_id, external_id)` 충돌을 막는다 |
| 미채택 | 태그(`code_change_kind.TAG`)는 페치하지 않는다. 릴리스가 태그를 포함하고, enum 값만 예약해 둔다 |

### 4.6 멱등 upsert SQL 패턴

6개 원천 연동 테이블에 동일 형태를 쓴다. `issue` 예시:

```sql
insert into issue (id, project_id, tool_connection_id, external_id, external_url, source_kind,
                   issue_key, title, body, status, severity, assignee,
                   source_created_at, source_updated_at, resolved_at, created_at, updated_at)
values (gen_random_uuid(), :projectId, :connectionId, :externalId, :externalUrl, 'TOOL',
        :issueKey, :title, :body, :status, :severity, :assignee,
        :sourceCreatedAt, :sourceUpdatedAt, :resolvedAt, now(), now())
on conflict (tool_connection_id, external_id)
        where tool_connection_id is not null and external_id is not null
do update set
        title = excluded.title, body = excluded.body, status = excluded.status,
        severity = excluded.severity, assignee = excluded.assignee,
        external_url = excluded.external_url,
        source_updated_at = excluded.source_updated_at, resolved_at = excluded.resolved_at,
        updated_at = now()
  where issue.title is distinct from excluded.title
     or issue.status is distinct from excluded.status
     or issue.severity is distinct from excluded.severity
     or issue.assignee is distinct from excluded.assignee
     or issue.resolved_at is distinct from excluded.resolved_at
returning id, (xmax = 0) as inserted, status;
```

| 규칙 | 이유 |
| --- | --- |
| `on conflict` 추론절에 인덱스 술어를 그대로 적는다 | 부분 유니크 인덱스는 술어 없이는 추론되지 않는다 |
| `do update ... where <is distinct from>` | 값이 안 바뀐 행은 UPDATE 자체가 일어나지 않아 `updated_at` 이 요동치지 않고 `entity_history` 도 비지 않는다 |
| `returning id, (xmax = 0) as inserted` | `stats_json.promotedInserted` / `promotedUpdated` 를 추가 쿼리 없이 집계 |
| `entity_history` | `StandardEntityService` 가 upsert 전 기존 행의 감사 대상 필드를 읽어 두었다가 `recordDiff` 로 변경분만 append (같은 트랜잭션, INV-16) |

### 4.7 재시도·백오프·실패 격리

| 대상 | 정책 |
| --- | --- |
| 도구 429 / 5xx / `IOException` / 타임아웃 | `Backoff.retry` — 1s → 2s → 4s → 8s → 16s, 지터 ±20%, 최대 5회. `Retry-After` 헤더가 있으면 그 값을 우선한다 |
| 도구 401/403 | 재시도 없음 → `ToolAuthException` → 잡 `FAILED`, `error_code=TOOL_AUTH_FAILED`, `error` 에 응답 본문 원문 저장, `tool_connection.status='FAILED'` + `last_error` 갱신 |
| 도구 404 | 재시도 없음 → `TOOL_RESOURCE_NOT_FOUND` |
| 레코드 1건 매핑 실패 | 예외 아님. `stats.unmapped++` 후 다음 레코드 계속 (INV-21) |
| 페이로드 1MB 초과 | 저장하지 않고 `stats.unmapped++` |
| 색인 실패 | 잡 `FAILED`. 커서 미전진이므로 다음 회차가 같은 소스를 재색인한다 |
| HTTP 타임아웃 | 연결 5초, 응답 30초 (`axlink.integration.*`) |

---

## 5. 시맨틱 레이어 물리 설계

### 5.1 카탈로그 로딩

`CatalogRegistry.load()` 가 `ApplicationReadyEvent` 에서 3테이블(`status='ACTIVE'`)을 전량 읽어 `Map<String, MeasureDef>` · `Map<String, DimensionDef>` · `Map<String, FilterDef>`(키 `field + "__" + op`)를 `Map.copyOf` 로 고정한다. **런타임 갱신 API 를 두지 않는다** — 카탈로그를 바꾸는 경로는 Flyway 마이그레이션뿐이므로(데이터모델 §2.5) 재기동이 곧 반영이다. 캐시 무효화 로직·TTL·`@Scheduled` refresh 를 만들지 않는다.

로딩 실패(행 0건, 참조 무결성 깨짐 — measure 의 `allowed_dimensions` 에 없는 dimension 키가 있음)는 **기동 실패**로 처리한다.

### 5.2 `spec_json` 검증 (INV-24, API §5.1 V1~V7)

`WidgetSpecValidator.validate(spec, allowedProjectIds)` 순서 — 바꾸지 않는다.

| # | 검증 | 실패 코드 |
| --- | --- | --- |
| V1 | `template` ∈ `WidgetTemplate` 8종 | `VALIDATION_FAILED` |
| V2 | `measure` ∈ `CatalogRegistry.activeMeasures()` | `CATALOG_VALIDATION_FAILED` |
| V3 | `dimensions ⊆ measure.allowedDimensions()` | `CATALOG_VALIDATION_FAILED` |
| V4 | `(field, op) ∈ measure.allowedFilters()` | `CATALOG_VALIDATION_FAILED` |
| V5 | `value` 타입이 `FilterDef.valueType` 과 일치. `ENUM_LIST` 면 `enumValues` 포함 검사, `UUID_LIST` 면 `UUID.fromString` 성공 | `CATALOG_VALIDATION_FAILED` |
| V6 | `projectScope = resolveScope(principal, spec.projectScope)` — **축소만** | 공집합이면 `PROJECT_ACCESS_DENIED` |
| V7 | `dimensions.size() <= 2`, `filters.size() <= 5` | `VALIDATION_FAILED` |

반환 `ValidatedSpec` 은 **문자열이 아니라 카탈로그 객체 참조**를 담는다: `record ValidatedSpec(WidgetTemplate template, MeasureDef measure, List<DimensionDef> dimensions, List<BoundFilter> filters, Set<UUID> projectIds, WidgetOptions options)`. 이후 단계에 사용자 문자열이 흘러가지 않는 구조적 보장이다.

### 5.3 SQL 조립 (INV-26)

`SemanticQueryBuilder.build(ValidatedSpec, Set<UUID>)` 이 만드는 SQL 골격은 하나뿐이다(데이터모델 §7.1).

```
SELECT  {d0.selectExpr} AS d0 [, {d1.selectExpr} AS d1]
      [, {d0.labelExpr} AS d0_label]
      , {measure.valueExpr} AS value
  FROM  {measure.baseTable} e
        {measure.joinClause}
        {dimension.requiresJoin ...}   -- 중복 JOIN 문자열은 set 으로 dedupe
 WHERE  e.project_id = ANY(:allowedProjectIds)
   [AND {measure.rowFilter}]
   [AND {filterFragment_i}]
 [GROUP BY d0[, d1]]
 ORDER BY value {ASC|DESC}
 LIMIT  :limit
```

**문자열이 SQL 에 들어가는 경로는 정확히 3종뿐이며 전부 카탈로그 컬럼 값이다**: `measure.{baseTable, joinClause, rowFilter, valueExpr}`, `dimension.{selectExpr, labelExpr, requiresJoin}`, `filter.columnExpr`. 이 컬럼들은 쓰기 API 가 없고 Flyway 시드로만 채워진다.

| 규칙 | 구현 |
| --- | --- |
| 식별자 치환 | 카탈로그 객체에서 꺼낸 값만. `spec` 의 문자열은 **키 조회에만** 쓰이고 SQL 로 전달되지 않는다 |
| 값 바인딩 | 전부 명명 파라미터 `:p0` … `:pN`. `FilterBinder` 가 `op` 별로 조각+파라미터를 만든다(데이터모델 §7.1 표) |
| 권한 필터 | `WHERE` 절 **첫 조건**으로 빌더가 무조건 부착. `build` 시그니처가 `allowedProjectIds` 를 요구하므로 빠뜨릴 수 없다 |
| `<TIME_COL>` | `TimeColumns.of(measure.baseTable())` 로 치환. dimension·filter 양쪽에 동일 값 사용 |
| `limit` | `options.limit` (기본 50, 상한 100). `data-table`·`progress-list` 외 템플릿은 상한 20 |
| ArchUnit | `SemanticQueryBuilder` 밖에서 `JdbcClient.sql(...)` 인자로 `+` 연결이 나타나지 않는지 검증 |

`IN_MONTH` 의 `"current"` 토큰은 빌더가 `LocalDate.now(clock)` 으로 치환한 뒤 `:pN` 에 바인딩한다 — 토큰 문자열이 SQL 에 그대로 들어가지 않는다.

### 5.4 `op` 별 바인딩 (`FilterBinder`)

| `op` | SQL 조각 | 파라미터 |
| --- | --- | --- |
| `IN` | `{columnExpr} = ANY(:pN)` | `UUID[]` 또는 `String[]` |
| `EQ` | `{columnExpr} = :pN` | 스칼라 |
| `GTE` / `LTE` | `{columnExpr} >= :pN` / `<= :pN` | 스칼라 |
| `BETWEEN` | `{columnExpr} between :pN and :pN1` | `LocalDate` 2건 |
| `IN_MONTH` | `date_trunc('month', {columnExpr}) = date_trunc('month', :pN::date)` | `LocalDate` |
| `LAST_N_DAYS` | `{columnExpr} >= now() - make_interval(days => :pN)` | `int` (문자열 연접 대신 `make_interval` 로 정수 바인딩) |

### 5.5 결과 → 위젯 데이터

`WidgetDataAssembler` 가 템플릿별로 `WidgetDataResponse` 를 만든다.

| 템플릿 | 변환 |
| --- | --- |
| `STAT_CARD` | dimension 없이 실행 → `total` 1행. `options.compareWithPrevious` 면 기간 필터를 직전 동일 길이로 이동해 1회 더 실행 → `previousTotal` |
| `BAR_CHART`·`PIE_CHART` | `columns = [d0(label), value]`, `rows` 그대로 |
| `LINE_CHART` | dimension 중 `value_type = TIME` 인 축을 x 로 강제. 시간 축이 없으면 `VALIDATION_FAILED` |
| `PROGRESS_LIST` | `columns = [d0, value]` + `unit='%'` 강제 |
| `DATA_TABLE` | `options.columns` 화이트리스트로 컬럼 축소 |
| `CHECKLIST` | `work_product_*` measure 전용. 22행 고정 |
| `GANTT_SUMMARY` | `schedule_variance_pct` + `period_*` dimension 조합 전용 |
| 공통 | `appliedProjectIds` = V6 축소 결과, `truncated` = `rows.size() == limit` |

---

## 6. RAG 물리 설계

### 6.1 청킹 (`ChunkingService`)

| 파라미터 | 값 |
| --- | --- |
| 토큰 추정 | `tokens ≈ ceil(chars / 2.4)` — 한/영 혼재 텍스트의 `bge-m3` 실측 근사. 토크나이저 의존성을 추가하지 않는다 |
| 목표 크기 | 800 토큰 |
| 최소 / 최대 | 200 / 1000 토큰. 200 미만 조각은 직전 청크에 병합 |
| 오버랩 | 15% (120 토큰) — 문장 경계에서 끊어 앞 청크 꼬리를 다음 청크 머리에 복제 |
| 표제 분할 | 1단계로 `^#{1,6}\s`, `^제\s*\d+\s*[장절]`, `^\d+(\.\d+)*\s` 패턴으로 섹션 분할 → `meta_json.headingPath` (최대 6단) |
| 문장 분할 | 2단계로 `(?<=[.!?。])\s+` + 개행 2회. 그리디 패킹 |
| 단일 청크 소스 | `REQUIREMENT`·`ISSUE`·`RISK`·`CHANGE_REQUEST`·`CORRECTION_ACTION`·`PROGRESS_RECORD` 는 데이터모델 §6.2 조합으로 1청크(초과 시에만 분할) |
| `page_no` | PDF 만. 추출기가 페이지 경계 마커를 남기고 청커가 시작 페이지를 `meta_json.pageNo` 로 기록 |
| 색인하지 않는 것 | `code_change` (데이터모델 §6.2) |

### 6.2 임베딩 포트

| 항목 | 값 |
| --- | --- |
| 차원 | **1024 고정**. `EmbeddingPort.dimension()` 이 반환 |
| 기동 검증 | `EmbeddingDimensionVerifier`(`rag` 패키지, `ApplicationReadyEvent`)가 `information_schema` 대신 `select atttypmod from pg_attribute where attrelid='doc_chunk'::regclass and attname='embedding'` 로 컬럼 차원을 읽어 비교. 불일치 시 `IllegalStateException` → **기동 실패** (INV-29) |
| 배치 | 32건. `POST /api/embed` `{model, input:[...]}` → `{embeddings:[[...]]}` |
| Ollama 어댑터 실패 | 연결 불가 → 재시도 없이 `AI_UNAVAILABLE`. 5xx → 200ms/400ms 2회 |
| Fake 구현 | `SHA-256(text)` 앞 8바이트를 `long` 시드 → `new Random(seed)` → `nextGaussian()` 1024개 → L2 정규화. **같은 입력이면 항상 같은 벡터**. `dimension()` 도 1024 를 반환하므로 차원 계약이 테스트로 고정된다 |

### 6.3 벡터 바인딩 (`VectorCodec`, `rag.repository`)

```java
static String toLiteral(float[] v)   // "[0.0123,-0.4,...]" — Locale.ROOT, 소수 6자리
static float[] fromString(String s)  // pgvector 텍스트 출력 파싱
```

SQL 에서는 항상 `:qvec::vector` 로 캐스트해 바인딩한다. `com.pgvector` 의존성을 추가하지 않는다.

### 6.4 하이브리드 검색 (`HybridSearchRepository`)

시그니처: `RetrievalSet search(float[] queryVector, String queryText, Collection<UUID> projectIds, int perList, int finalLimit)` — `projectIds` 없는 오버로드를 만들지 않는다(INV-04).

벡터 쿼리는 세션 파라미터가 필요하므로 **한 커넥션 안에서** 실행한다.

```sql
-- 같은 트랜잭션(=같은 커넥션) 안에서 순서대로
SET LOCAL hnsw.ef_search = 100;
SET LOCAL hnsw.iterative_scan = relaxed_order;

SELECT id, project_id, source_type, source_id, source_title, source_uri,
       content, meta_json, 1 - (embedding <=> :qvec::vector) AS score
  FROM doc_chunk
 WHERE project_id = ANY(:projectIds)
 ORDER BY embedding <=> :qvec::vector
 LIMIT :perList;
```

```sql
SELECT id, project_id, source_type, source_id, source_title, source_uri,
       content, meta_json,
       greatest(ts_rank_cd(content_tsv, plainto_tsquery('simple', :q)),
                similarity(content, :q)) AS score
  FROM doc_chunk
 WHERE project_id = ANY(:projectIds)
   AND (content_tsv @@ plainto_tsquery('simple', :q) OR content % :q)
 ORDER BY score DESC
 LIMIT :perList;
```

| 항목 | 확정 |
| --- | --- |
| 병렬 실행 | 두 쿼리를 `ragExecutor` 에서 `CompletableFuture` 2건으로 동시 실행. 벡터 쿼리는 `SET LOCAL` 때문에 `@Transactional(readOnly = true)` 로 커넥션을 고정한다 |
| 융합 | `RRF: score(d) = Σ 1/(60 + rank_i(d))`, `k = 60` 고정. `perList = 40`, `finalLimit = 8` |
| 동점 처리 | RRF 동점이면 벡터 순위가 앞선 쪽 |
| 빈 결과 | `RetrievalSet.isEmpty()` → LLM 호출 없이 고정 응답(§6.6) |
| `%` 연산자 | `pg_trgm.similarity_threshold` 기본 0.3 대신 `SET LOCAL pg_trgm.similarity_threshold = 0.1` 을 어휘 쿼리 앞에 붙인다(데이터모델 §6.3 의 `similarity > 0.1` 기준과 일치시킨다) |

### 6.5 컨텍스트 조립

```
[고정 system 프롬프트]                          ← Prompts.SYNTHESIS_SYSTEM, 바이트 불변
[고정 출력 규격 설명(각주 [n] 규칙)]
[집계 컨텍스트]  route ∈ {AGGREGATE, MIXED} 일 때만. 표 형태 텍스트
[근거 청크 1..8]  "[n] {sourceTitle} · {headingPath|pageNo}\n{content(≤1KB)}"
[대화 이력]      직전 3턴 원문 + 그 이전은 요약 1문단
[사용자 질의]
```

프리픽스 안정성을 위해 system 프롬프트에 타임스탬프·사용자명·프로젝트 ID 를 넣지 않는다(아키텍처 §3.4, INV-04).

### 6.6 SSE 스트리밍 컨트롤러 구조

```
AskController.ask(conversationId, AskRequest, principal)
  ├─ ProjectAccessResolver.resolveScope(principal, req.projectScope())   [요청 스레드]
  ├─ ConversationService.appendUserMessage(...)                           [요청 스레드, T1]
  ├─ SseEmitter emitter = new SseEmitter(190_000L)
  ├─ SseSink sink = new SseSink(emitter, sseHeartbeatScheduler)           15초 ping 등록
  ├─ ragExecutor.execute(() -> ragOrchestrator.ask(ctx, sink))
  └─ return emitter
```

| 항목 | 확정 |
| --- | --- |
| 이벤트 순서 | `start` → `delta`* → `sources` → `done`. 실패 시 어느 지점에서든 `error` 1건 후 `complete()` |
| `assistantMessageId` | `start` 이벤트 전에 서버가 `UUID.randomUUID()` 로 미리 발급 |
| 하트비트 | `sseHeartbeatScheduler.scheduleAtFixedRate(15s)` → `event: ping`, `data: {}`. `done`/`error` 시 취소 |
| 중지 감지 | `emitter.onError`/`onCompletion` → `sink.close()` → `SseSink.isClosed()` 가 true. `OllamaLlmAdapter` 의 스트림 루프가 매 델타마다 이 값을 확인하고 true 면 `InputStream.close()` 후 즉시 반환 |
| 중지 시 저장 | **assistant 메시지를 저장하지 않는다.** user 메시지는 이미 T1 에서 저장됨 |
| 별도 abort 엔드포인트 | 만들지 않는다 |
| 트랜잭션 | 스트리밍 전체를 트랜잭션으로 감싸지 않는다. `message` + `message_source` 저장이 마지막 1 트랜잭션 |
| 근거 0건 | `delta` 로 고정 문구 1건 → `sources: []` → `done{finishReason:"no_evidence"}`. LLM 호출 없음 |

### 6.7 출처(`message_source`) 기록

`AnswerPostProcessor.process(rawText, retrievalSet)` 가 합성 완료 직후 실행된다.

| # | 처리 |
| --- | --- |
| 1 | 본문에서 `\[(\d{1,2})\]` 를 스캔해 등장 순서대로 수집 |
| 2 | 각 `[n]` 이 `RetrievalSet` 의 n번째 청크에 대응하는지 확인. 범위 밖·중복 없는 번호는 **본문에서 해당 표기를 제거** (INV-31/32) |
| 3 | 살아남은 각주를 1부터 재번호(빈 번호가 생기지 않게) 후 본문 치환 |
| 4 | 재번호 결과로 `message_source` 행 생성 — `footnote_no`, `doc_chunk_id`, `source_type`, `source_title`, `snippet`(청크 본문 앞 300자), `external_url`(`source_uri`), `page_no`(`meta_json.pageNo`) **스냅샷 저장** |
| 5 | `message`(role=ASSISTANT, content=후처리 본문, route_type, rewritten_query, latency_ms) + `message_source` × n 을 **1 트랜잭션**으로 insert |
| 6 | `sources` 이벤트 → `done` 이벤트 |

프론트는 `done` 이후 `GET /api/conversations/{id}/messages` 로 최종본을 다시 읽는다(API §4.3) — 각주 제거로 본문이 바뀌기 때문이다.

---

## 7. 설정 파일

### 7.1 `src/main/resources/application.yml`

```yaml
spring:
  application:
    name: axlink
  datasource:
    url: jdbc:postgresql://localhost:5432/axlink
    username: ${AXLINK_DB_USER:userinsight-design}
    password: ${AXLINK_DB_PASSWORD:}
    hikari:
      maximum-pool-size: 16
      minimum-idle: 4
      connection-timeout: 5000
      max-lifetime: 1200000
      pool-name: axlink-pool
  flyway:
    enabled: true
    locations: classpath:db/migration
    baseline-on-migrate: false
    validate-on-migrate: true
  jackson:
    time-zone: UTC
    default-property-inclusion: always
    serialization:
      write-dates-as-timestamps: false
      fail-on-empty-beans: false
    deserialization:
      fail-on-unknown-properties: true
  servlet:
    multipart:
      max-file-size: 50MB
      max-request-size: 52MB
  mvc:
    async:
      request-timeout: 200000
  threads:
    virtual:
      enabled: false

server:
  port: 8080
  servlet:
    encoding:
      charset: UTF-8
      force: true
  compression:
    enabled: false

logging:
  level:
    root: INFO
    kr.co.axlink: DEBUG
    org.springframework.jdbc.core.JdbcTemplate: INFO
    org.flywaydb: INFO
  pattern:
    console: "%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n"

axlink:
  security:
    jwt:
      secret: ${AXLINK_JWT_SECRET:}          # Base64 32바이트 이상. 미설정 시 기동 실패
      issuer: axlink
      access-ttl: PT30M
      refresh-ttl: P14D
    cors:
      allowed-origins: http://localhost:5173
  crypto:
    master-key: ${AXLINK_SECRET_KEY:}        # Base64 32바이트. 미설정 시 기동 실패
  storage:
    root: ${AXLINK_STORAGE_ROOT:./var/uploads}
  ai:
    provider: ollama                          # ollama | fake
    base-url: http://localhost:11434
    connect-timeout: PT5S
    embedding-timeout: PT30S
    synthesis-timeout: PT180S
    models:
      synthesis: glm-5.2:cloud
      structuring: deepseek-v4-pro:cloud
      embedding: bge-m3
    embedding-dimension: 1024
    embedding-batch-size: 32
    retry:
      max-attempts: 2
      initial-delay: PT0.2S
  rag:
    per-list-limit: 40
    final-limit: 8
    rrf-k: 60
    hnsw-ef-search: 100
    trgm-threshold: 0.1
    chunk-target-tokens: 800
    chunk-min-tokens: 200
    chunk-max-tokens: 1000
    chunk-overlap-ratio: 0.15
    context-chars-per-chunk: 1024
    history-turns: 3
    sse-timeout: PT190S
    sse-heartbeat: PT15S
  semantic:
    default-limit: 50
    max-limit: 100
  integration:
    poll-interval-ms: 900000
    cursor-overlap: PT60S
    connect-timeout: PT5S
    read-timeout: PT30S
    page-size: 100
    max-payload-bytes: 1048576
    retry:
      max-attempts: 5
      initial-delay: PT1S
      max-delay: PT16S
      jitter-ratio: 0.2
    job-retention-days: 90
```

### 7.2 `src/test/resources/application.yml`

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/axlink_test
    username: ${AXLINK_DB_USER:userinsight-design}
    password: ${AXLINK_DB_PASSWORD:}
  flyway:
    clean-disabled: false

axlink:
  ai:
    provider: fake
  security:
    jwt:
      secret: dGVzdC1vbmx5LXNlY3JldC1rZXktMzItYnl0ZXMtbG9uZyE=
  crypto:
    master-key: dGVzdC1vbmx5LW1hc3Rlci1rZXktMzItYnl0ZXMtISEh
  storage:
    root: ./build/test-uploads

logging:
  level:
    kr.co.axlink: INFO
```

### 7.3 환경변수 오버라이드 규칙

| 규칙 | 내용 |
| --- | --- |
| 우선순위 | 커맨드라인 `--key=value` > 환경변수 > `application-{profile}.yml` > `application.yml` (Spring Boot 기본) |
| 이름 변환 | `axlink.ai.base-url` → `AXLINK_AI_BASEURL`. 하이픈은 제거되고 점은 `_` 가 된다 |
| 비밀값 | `AXLINK_JWT_SECRET`, `AXLINK_SECRET_KEY`, `AXLINK_DB_PASSWORD` **3개는 yml 에 기본값을 두지 않는다.** 빈 값이면 `@ConfigurationProperties` 의 `@NotBlank` 검증이 기동을 실패시킨다 |
| 프로파일 | `dev`(기본, CORS 허용) / `test`(Gradle `test` 태스크가 지정) / `prod`(CORS 비활성, `logging.level.kr.co.axlink=INFO`). `application-prod.yml` 은 이 2개 키만 갖는다 |
| 금지 | 프로파일별 파일에 DB URL·모델 ID 를 중복 정의하지 않는다. 환경별 차이는 환경변수로만 준다 |

---

## 8. 테스트 물리 전략

### 8.1 단위 테스트 (Spring 컨텍스트 없음, `axlink_test` DB 불필요)

| 대상 클래스 | 검증 내용 |
| --- | --- |
| `WidgetSpecValidator` | V1~V7 각각의 위반 케이스와 통과 케이스. 카탈로그는 in-memory `CatalogRegistry` 스텁 |
| `SemanticQueryBuilder` | 생성된 SQL 문자열에 `project_id = ANY(:allowedProjectIds)` 가 항상 포함되는지, 파라미터 맵 키가 조각과 일치하는지, dimension 0/1/2개 각각의 GROUP BY |
| `FilterBinder` | `op` 7종 × `valueType` 5종 조합의 조각·바인딩 |
| `TimeColumns` | `base_table` 8종 전부 매핑 존재 |
| `MappingRuleEngine` | Jira/GitLab 픽스처 JSON → `StandardChange`. 규칙 미매치가 예외가 아니라 `Optional.empty()` (INV-21) |
| `ChunkingService` | 표제 분할·오버랩 비율·최소 병합·최대 초과 없음. 동일 입력 → 동일 청크(결정성) |
| `AnswerPostProcessor` | 범위 밖 각주 제거, 재번호, `message_source` 대응 1:1 (INV-31/32) |
| `RrfFusion`(`HybridSearchService` 내부 static) | 두 리스트 융합 순위가 `Σ 1/(60+rank)` 와 일치 |
| `SecretCipher` | encrypt→decrypt 왕복, IV 가 매번 다른지, 손상된 입력이 예외인지 |
| `Backoff` | 지연 수열·지터 범위·재시도 불가 예외 즉시 전파 |
| `RiskService.severityOf` | `probability × impact` 16조합 |
| 상태 enum 12종 | `canTransitionTo` 전이표(INV-15) 전수 |
| `FakeEmbeddingAdapter` | 1024차원, L2 노름 1.0, 동일 입력 동일 벡터 |
| `FakeLlmAdapter` | `callTool` 이 enum 첫 값을 채운 인자를 반환 |
| `SortSpec` | 화이트리스트 밖 필드 400, 다중 정렬 순서 |
| `JiraJql` / `GitLabResources` | JQL 문자열·URL 인코딩 |
| `VectorCodec` | `float[]` → literal → `float[]` 왕복 |

### 8.2 통합 테스트 (`@SpringBootTest` + 로컬 PostgreSQL `axlink_test`)

**DB 준비**

```bash
createdb axlink_test
psql -d axlink_test -c "create extension if not exists vector; create extension if not exists pg_trgm; create extension if not exists pgcrypto;"
```

확장 생성은 슈퍼유저 권한이 필요하므로 **테스트 실행 전 1회 수동 수행**하고, 테이블은 Flyway 가 만든다. `README` 에 이 두 줄을 적는다. Testcontainers 를 쓰지 않는 이유는 Docker 가 없는 환경 제약 때문이다.

| 항목 | 방식 |
| --- | --- |
| 스키마 | Flyway V1~V10 을 테스트 컨텍스트 기동 시 실행. `spring.flyway.clean-disabled: false` |
| 격리 | 테스트 클래스마다 `@Transactional` + 롤백. **예외**: `SyncRunnerIT`(다중 트랜잭션), `IndexingServiceIT`(별도 트랜잭션) 는 `@Transactional` 없이 실행하고 `@AfterEach` 에서 `TestDataCleaner.truncateAll()` 로 정리 |
| AI | `axlink.ai.provider=fake` 고정 → Ollama 데몬 없이 전 테스트 통과 |
| 외부 도구 | `JiraHttpClient`/`GitLabHttpClient` 만 `@MockitoBean` 으로 대체하고 저장된 응답 JSON 픽스처를 반환. `ToolConnector` 이상 계층은 실제 코드 |

**통합 테스트 대상 클래스**

| 테스트 클래스 | 대상 |
| --- | --- |
| `FlywayMigrationIT` | V1~V10 전체 적용 + 제약·인덱스 존재 확인(`ck_work_product__type` 22값, `uq_*__source` 6건, HNSW·GIN 인덱스 3건) |
| `AuthFlowIT` | 로그인 → me → refresh 회전 → 재사용 감지 → 로그아웃 |
| `ProjectCreationIT` | UC-03: project 1행 + work_product 22행 + 기본 dashboard 1행 (INV-12) |
| `ProjectAccessResolverIT` | 역할 3종 × 할당 상태별 `allowedProjectIds` |
| `ProjectClosureIT` | INV-07 게이트 3조건 각각의 차단과 통과 |
| `ToolConnectionIT` | 인증정보 암호화 저장, 응답 마스킹(INV-06), `uq_tool_connection__target` 충돌 409 |
| `SyncRunnerIT` | 픽스처 재생 → raw_artifact upsert → 표준 upsert → 색인 → 커서 전진. **두 번 실행해도 결과 동일**(INV-14 멱등) |
| `SyncJobConcurrencyIT` | 동일 연결에 잡 2건 동시 claim → 1건만 RUNNING (INV-22) |
| `SyncFailureIT` | 401 픽스처 → 잡 FAILED, `last_synced_at` 불변 (INV-23) |
| `StandardEntityHistoryIT` | 값이 바뀐 필드만 `entity_history` append, `UPDATE`/`DELETE` 권한 회수 확인 (INV-16) |
| `SemanticQueryExecutorIT` | measure 13종 전부 실제 실행 → SQL 문법·컬럼 존재 검증. **카탈로그 시드가 깨지면 여기서 잡힌다** |
| `SemanticScopeIT` | 타 프로젝트 데이터가 결과에 절대 섞이지 않음 (INV-04) |
| `DashboardLayoutIT` | `layout_json.i` 와 ACTIVE 위젯 id 불일치 항목 제거 후 저장 |
| `WidgetGenerationIT` | Fake LLM tool 인자 → 검증 → 미리보기까지. `NOT_EXPRESSIBLE` 분기 |
| `IndexingServiceIT` | 재색인이 delete+insert 전량 교체인지, `uq_doc_chunk__source` 위반 없음, 1024차원 저장 |
| `HybridSearchIT` | 벡터+FTS+trgm 3경로 각각 결과가 나오는지, `project_id` 필터가 항상 적용되는지, RRF 상위 8건 |
| `AskSseIT` | `MockMvc` 비동기 + Fake LLM: 이벤트 순서 start→delta→sources→done, 근거 0건 분기 |
| `DocumentPipelineIT` | 샘플 PDF·DOCX 업로드 → 추출 → Fake 정형화 → 초안 → 확정 → work_product/requirement/doc_chunk 생성 (INV-33) |
| `WorkProductTypeRejectedIT` | 22종 밖 유형 반환 시 `type_rejected=true` + 422 |
| `ErrorContractIT` | 대표 4xx/5xx 전부 `ErrorResponse` 5필드를 채워 반환 |

### 8.3 아키텍처 테스트 (ArchUnit, 6건)

| 테스트 | 규칙 |
| --- | --- |
| `LayerDependencyTest` | `..domain..` 이 `..web..`·`..repository..`·Spring·Jackson 을 참조하지 않는다 |
| `TransactionBoundaryTest` | `@Transactional` 은 `..service..` 클래스에만 존재 |
| `ProjectScopeParameterTest` | `HybridSearchRepository`·`SemanticQueryBuilder` 의 모든 public 메서드가 `Collection<UUID>`(또는 `Set<UUID>`) 인자를 갖는다 (INV-04) |
| `NoSqlConcatenationTest` | `..repository..`·`..semantic..` 에서 `JdbcClient.sql(...)` 인자에 `String` 연접이 없다 (INV-26). `SemanticQueryBuilder` 는 예외 대상이되 카탈로그 필드 외 입력을 참조하지 않는지 별도 확인 |
| `AiAdapterCountTest` | `kr.co.axlink.ai.adapter..` 의 `LlmPort` 구현체 수 == 2, `EmbeddingPort` 구현체 수 == 2 (INV-35) |
| `NoFormatParameterTest` | `OllamaLlmAdapter` 소스에 `"format"` 리터럴이 없다 (INV-34) |

### 8.4 계약 일치 테스트 (INV-18)

`EnumContractTest` — `frontend/src/standard/*.ts` 를 정규식으로 파싱해 문자열 리터럴 집합을 만들고 Java enum 값 집합과 비교한다. 대상: `WorkProductType`(22), `Iso29110Activity`(10), `ProjectStatus`, `WidgetTemplate`(8), `RequirementStatus`, `IssueStatus`, `WorkProductStatus`, `RiskStatus`, `ChangeRequestStatus`, `CorrectionStatus`, `Role`, `OrgType`, `SyncJobStatus`, `SyncJobKind`, `DocumentUploadStatus`, `FilterOp` 등 데이터모델 §3 전 enum. 불일치 시 **테스트 실패**.

### 8.5 픽스처 전략

| 종류 | 위치 | 방식 |
| --- | --- | --- |
| 도구 응답 | `src/test/resources/fixtures/jira/*.json`, `fixtures/gitlab/*.json` | 실제 API 응답을 익명화해 저장. `FixtureLoader.load(String path, Class<T>)` |
| 업로드 문서 | `src/test/resources/fixtures/documents/` | 소형 PDF·DOCX·XLSX·HWP 각 1개 |
| DB 시드 | `src/test/java/.../support/Fixtures.java` | **SQL 파일이 아니라 빌더 메서드.** `Fixtures.clientOrg()`, `.contractorOrg()`, `.project(clientOrgId)`, `.assignment(projectId, userId)`, `.connection(projectId)`, `.issue(projectId, n)`, `.chunk(projectId, text)` — 각각 저장 후 id 반환. SQL 파일로 두면 컬럼 추가 때마다 전 파일을 고쳐야 한다 |
| 카탈로그 | Flyway `V9__semantic_seed.sql` 그대로 | 테스트가 시드를 재정의하지 않는다. `SemanticQueryExecutorIT` 가 운영 시드를 그대로 검증하는 것이 목적이다 |
| 인증 | `TestAuth.bearerFor(UUID userId, Role role, UUID orgId)` — 실제 `JwtIssuer` 로 토큰 발급. `@WithMockUser` 를 쓰지 않는다(`AuthPrincipal` 이 principal 이어야 한다) |
| 정리 | `TestDataCleaner.truncateAll()` — `truncate ... restart identity cascade` 를 FK 역순으로. `flyway_schema_history` 와 `semantic_*` 3테이블은 제외 |

### 8.6 커버리지·실행

| 항목 | 값 |
| --- | --- |
| 실행 | `./gradlew test` — 단위 + 통합 + ArchUnit 전부. 태스크를 쪼개지 않는다(로컬 PostgreSQL 이 전제 환경이다) |
| 목표 | 커버리지 수치 게이트를 두지 않는다. 위 §8.1~8.4 목록이 곧 게이트다 |
| CI | 1차 릴리스 범위에 CI 파이프라인이 없다. 추가 시 `createdb axlink_test` + 확장 3개 생성만 선행하면 그대로 돈다 |

---

## 9. 후속 문서로 넘기는 항목

| 항목 | 후속 문서 |
| --- | --- |
| `ToolSchema` 4종 JSON Schema 전문, system 프롬프트 본문 | `04-physical-ai` |
| Flyway V1~V10 SQL 전문 | `03-physical-migration` |
| 라우트 트리, 위젯 렌더러 8종 props, shadcn 설치 목록 | `03-physical-frontend` |
