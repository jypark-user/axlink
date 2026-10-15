# ARC-026 실행 이미지를 GitHub Actions 에서 빌드해 GHCR 에 올린다

| 항목 | 내용 |
|---|---|
| 상태 | **확정** (2026-10-15). 10-15 오전에 보류했다가 같은 날 오후 사용자 결정으로 보류를 풀었다 |
| 범위 | 이미지 빌드·검사·게시까지. **서버 배포는 하지 않는다.** 5173·5174 반영은 사람이 digest 를 골라 따로 한다 |
| 관련 | SER.SEC.002(반입 요소 문서화, GH-40), SWFR.DEM.001, GH-51(인도) |
| 선행 | `docs/40-manual/배포-운영-절차.md`, `docs/00-management/실행-환경-운영.md`, `로컬-실행.md` 3절 |

## 1. 왜 바꾸나

- 개발 PC 가 불안정하다. 웹 이미지 빌드 중 node 세그폴트(10-14), 빌드 산출물 CRC 오류(10-01), 도커 VM 커널 패닉(10-13·10-14·10-15)이 났다. 빌드를 PC 에서 하는 한 반영이 PC 상태에 묶이고, 손상된 이미지가 만들어질 위험이 있다.
- 이미지가 그 PC 에만 있어 PC 가 고장 나면 실행본도 잃는다.
- 태그를 손으로 붙여 커밋하지 않은 변경으로 만든 이미지(`0.3.3-0df59f9-guide`)가 섞였다.

## 2. 흐름

```
PR            → images.yml 검사: 빌드·내용 검사·기동 검증·취약점 보고. 게시 안 함(읽기 권한)
main 병합     → ci.yml 성공 → images.yml 게시: 같은 커밋을 빌드·검사 → sha-<7>·main 태그로 GHCR
vX.Y.Z 태그   → main 에 있고 CI 가 성공한 커밋인지 확인 → X.Y.Z·sha-<7> 태그 + 반입용 tar·체크섬
수동 실행     → 검사만. publish 를 켜면 main·v태그에서만 게시
서버          → 사람이 image-manifest.json 의 digest 를 골라 pull → 지금의 반영 절차(백업·마이그레이션·재생성)
```

| 파일 | 하는 일 |
|---|---|
| `.github/workflows/images.yml` | 언제 무엇을 할지(트리거·권한). 검사와 게시를 다른 작업·다른 권한으로 나눈다 |
| `.github/workflows/image-build.yml` | 빌드·검사·게시 본체(재사용 워크플로) |
| `.github/scripts/image-smoke.sh` | 기동 검증 |
| `infra/docker-compose.ghcr-ext.yml`·`ghcr-int.yml` | 5173·5174 를 GHCR 이미지(digest)로 띄울 때 덮어쓰는 파일. **지금 실행 환경에는 쓰지 않는다** |

## 3. 이미지와 태그

- 레지스트리: `ghcr.io/jypark-user/axlink-{api,web,migrate}`. 저장소가 비공개라 패키지도 비공개다(첫 게시 뒤 확인, 7절).
- 플랫폼 `linux/amd64`. GitHub 호스트 러너(ubuntu-latest)에서 빌드한다. 이 PC 를 self-hosted runner 로 쓰지 않는다.
- 웹은 앱 경로 `/ax-link/` 로 빌드한다. 5173·5174 모두 이 경로로 연다.

| 태그 | 언제 | 바뀌나 | 쓰임 |
|---|---|---|---|
| `sha-<커밋7>` | main·릴리스 게시 | 안 바뀐다 | 반영·되돌리기 지정 |
| `X.Y.Z` | v태그 | 안 바뀐다 | 릴리스·인도 |
| `main` | main 게시 | 바뀐다 | "가장 최근 main" 확인용. **반영에 쓰지 않는다** |
| digest `sha256:…` | 모든 게시 | 안 바뀐다 | 반영 때 Compose 에 적는 값 |

이미지 안 버전 표시(API 헬스·웹 `version.json`): 릴리스는 `X.Y.Z`, main 은 `main-<커밋7>`, PR 은 `pr<번호>-<커밋7>`. 라벨 `org.opencontainers.image.revision` 에 전체 커밋을 넣고 검사한다.

## 4. 검사

### 4-1. 빌드 문맥

`.dockerignore` 를 그대로 적용한 문맥을 통째로 담아 금지 항목을 찾는다. 실제 빌드가 받는 파일과 같다.
금지: `.env`(예시 제외), `*.dump`, `*.tar(.gz)`, `*.pem`·`*.key`·`*.p12`, `var/`, `.git/`, `.claude/`, `tests/`, `infra/`, 시험 계정 파일(`*accounts*.env`). 이번에 `.dockerignore` 에 덤프·tar·키 패턴을 더했다.

### 4-2. 이미지 내용

- 세 이미지 모두 revision 라벨이 빌드한 커밋과 같다.
- api: `app.main` 을 불러온다, 사용 안내 문서(`docs/40-manual/도구-연동-가이드.md`)가 있다, `.env`·덤프·시험 파일이 없다, uid 10001 로 돈다.
- migrate: 저장소의 V 파일 수와 이미지 안 수가 같다.
- web: `index.html` 이 `/ax-link/assets/` 를 부른다(빌드 안의 `check-build.mjs` 와 별도로 한 번 더).

### 4-3. 기동 검증 (`image-smoke.sh`)

러너 안에서 빈 시험 DB(tmpfs) → migrate → api(운영 모드, 이 실행에서만 만든 JWT·암호화 키, 가짜 임베딩, 스케줄러 끔) → web 순서로 올린다.

- 마이그레이션이 저장소 최신 번호까지 간다.
- API 헬스 버전 표시, 시험 계정 로그인, 사용 안내·사업 목록 200, 비로그인 401.
- 웹 `/ax-link/` 와 그 화면이 부르는 JS·CSS 전부 200, `version.json` 버전, 웹을 거친 API 프록시, 목록 밖 호스트 421.

실패하면 컨테이너 로그를 14일 산출물로 남긴다.

### 4-4. 취약점 (Trivy, 고정 버전 이미지)

- 고칠 판이 나온 HIGH·CRITICAL 만 센다(`--ignore-unfixed`). 결과는 작업 요약과 산출물(30일)에 남는다.
- 처리 기준: PR·main 은 보고만 한다. **릴리스는 고칠 수 있는 CRITICAL 이 하나라도 있으면 멈춘다.** HIGH 는 릴리스 노트에 남기고 다음 기반 이미지 갱신 때 처리한다.

## 5. 기록

게시마다 `image-manifest.json`(산출물 90일)과 작업 요약에 남긴다: 커밋, 버전 표시, 태그, 앱 경로·플랫폼, 실행 링크, 이미지별 digest·이미지 id·크기.
반영 기록(`var/int-5174/이미지-기록.md` 등)에는 이 파일의 digest 를 옮겨 적는다.

## 6. 배포와의 분리

- 워크플로에 서버 접속 정보·SSH·배포 단계가 없다. 게시가 5173·5174 를 바꾸지 않는다.
- 공개 환경은 지금 이미지(`0.2.1-3784976`, 로컬 빌드)와 V48 을 그대로 쓴다.
- GHCR 이미지로 띄우는 덮어쓰기 파일(`docker-compose.ghcr-ext.yml`·`ghcr-int.yml`)은 준비만 했다. 이미지를 digest 로만 받는다(`AXLINK_API_IMAGE`·`AXLINK_WEB_IMAGE`).
- 로컬 이미지와 복구 설정은 그대로 둔다. 레지스트리를 쓸 수 없을 때 로컬 빌드가 대체 경로다.
- 5174 는 원격 게시를 확인한 뒤 별도 단계로 반영한다(`var/int-5174/반영안-2026-10-15.md` 를 digest 기준으로 고쳐 쓴다).

## 7. 권한과 비밀값

- 게시는 `GITHUB_TOKEN` 으로 한다. 게시 작업만 `packages: write`, 검사 작업은 `contents: read` 뿐이다. 새 비밀값을 저장소 설정에 넣지 않는다.
- 릴리스 확인은 `actions: read` 로 그 커밋의 CI 성공 기록을 읽는다.
- 기동 검증의 JWT·암호화 키는 그 실행에서 만들고 버린다. 출력하지 않는다.
- 운영 데이터(DB·문서)와 운영 키는 GHCR·Actions 산출물에 올리지 않는다.
- PC 에서 받을 때: `read:packages` 만 준 토큰으로 `docker login ghcr.io`. 토큰은 도커 자격 증명 저장소에만 둔다. 저장소·문서·채팅에 적지 않는다.
- 첫 게시 뒤 확인(사용자): GitHub → 프로필 → Packages 에서 세 패키지가 **Private** 인지, 저장소에 연결돼 있는지(라벨 `org.opencontainers.image.source`).

## 8. 반입용 tar

v태그 게시 때 `axlink-images-X.Y.Z.tar.gz`(세 이미지 `docker save`), 매니페스트, `SHA256SUMS` 를 산출물로 만든다(90일, 압축 없이 보관).
90일 뒤에도 남겨야 하는 인도본은 사람이 내려받아 인도 매체에 옮기거나 릴리스에 첨부한다. 자동으로 릴리스에 붙이지 않는다.

받는 쪽: `sha256sum -c SHA256SUMS` → `gunzip -c axlink-images-X.Y.Z.tar.gz | docker load` → `infra/docker-compose.prod.yml` 에 `AXLINK_IMAGE_PREFIX=ghcr.io/jypark-user`, `AXLINK_VERSION=X.Y.Z`.

## 9. 보존 정책 (제안, 자동 삭제는 아직 넣지 않음)

| 구분 | 무엇 | 보존 |
|---|---|---|
| CI 임시 | 시험 결과·기동 로그·취약점 결과 | 14~90일 산출물(자동 만료) |
| 게시 기록 | `image-manifest-*` | 90일 산출물 + 반영 기록에 digest 옮겨 적기 |
| main 이미지 | `sha-*` | 최근 30개 + 아래 보호 대상. 정리는 사람이 확인하고 한다 |
| 보호 | 지금 5173·5174 가 쓰는 것, 바로 전 것(되돌리기), 모든 `X.Y.Z` | 지우지 않는다 |
| 반입본 | 릴리스 tar | 산출물 90일 → 인도 매체·릴리스로 옮긴다 |

- 용량 추정: api 약 250MB, web 약 60MB, migrate 약 300MB(flyway 기반 이미지)로 커밋당 약 0.6GB(압축 전, 층을 나눠 쓰므로 실제 증가는 더 작다). main 병합이 하루 몇 건이면 한 달 수십 GB 가 될 수 있다. 첫 게시 뒤 실제 크기로 다시 잰다.
- Actions 사용량: 한 번 약 8~12분(캐시 적중 시 더 짧다). PR 은 경로 필터로 앱·도커 관련 변경에서만 돈다.
- 비공개 저장소라 GHCR 저장·전송과 Actions 시간이 계정 한도에 잡힌다. 한도·요금은 계정 설정에서 확인한다(7절과 같이 사용자 확인).
- 기존 패키지·릴리스 자료는 이번 작업에서 지우지 않았다.

## 10. 하지 않는 것

- 5173·5174 자동 배포.
- 개발 PC 빌드 금지. GHCR 를 쓸 수 없을 때의 대체 경로로 남긴다.
- 여러 플랫폼(arm64) 빌드.
- 이미지 서명(cosign)·SBOM 첨부. 인도 요건이 생기면 더한다.
