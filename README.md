# AX Link

> 2026년 AX 프로젝트 관리 운영 프레임워크 개발 용역
> 발주 (재)전주정보문화산업진흥원 · 수행 유저인사이트(주) · ~2026.11.30 · PoC

발주기관 담당자가 수행사의 형상관리·이슈도구·비정형 산출물을 직접 뒤지지 않고,
**자연어 질의와 대시보드만으로** 진척·일정·품질·요구사항 이행·산출물 현황을 확인하게 하는
프레임워크. 외부 클라우드 LLM에 의존하지 않고 **폐쇄망 온프레미스**로 동작한다.

## 이 저장소는 자기 자신을 관리한다

**이 저장소가 AX Link의 1번 샘플 프로젝트다.** 여기 남는 이슈·커밋·PR·산출물 문서가
곧 PoC의 수집 대상이자 시연 데이터다. 그래서 **규약을 어긴 커밋은 그 자체로 데이터 결함**이고,
나중에 소급 수정할 수 없다. 작업 전 [`CLAUDE.md`](./CLAUDE.md)를 읽는다.

## 구조

```
backend/     Spring Boot · JdbcClient (JPA 금지) · Flyway · pgvector
  …/integration/   [2] 커넥터 포트 + GitHub·Redmine 어댑터, 증분 수집
  …/standard/      [3] 표준 데이터 모델 · 추적관계
  …/dashboard/     [3][5] 지표 집계 · 위젯 템플릿 23종
  …/semantic/      [5] 시맨틱 레이어 — 화면·답변의 모든 수치가 여기서 나온다
  …/rag/ ai/ document/  [4] 청킹 · 임베딩 · 검색 · 근거 게이트 · 문서 추출
frontend/    [6] React + Vite — 발주기관용 읽기 전용 화면 + AI 질의
docs/        납품 산출물 겸 RAG 코퍼스
  00-management/  작업계획 · M1 합의서 · WBS
  10-requirements/ IM-001 요구사항정의서 · E2E 사용자 시나리오
  20-design/      파일럿 대조표 · 진척률 산정체계 · 인프라 배치방안
  90-pilot/       파일럿 원본 문서 — 참고자료, 납품 대상 아님
scripts/     추적표 생성 · GitHub 부트스트랩
infra/       docker-compose (PostgreSQL+pgvector · Redmine · Ollama)
```

## 절대 규칙

1. **LLM은 수치를 생성하지 않는다.** 모든 수치는 시맨틱 레이어의 결정론적 집계 결과다.
2. **LLM은 UI를 생성하지 않는다.** 인포 템플릿은 의도 해석 단계에서 *선택*된다.
3. **근거 없는 답변은 차단한다.** 유사도 미달 시 "근거 부족"으로 응답하고, 답변에는 출처가 붙는다.

메뉴 직접 접근과 자연어 질의는 동일한 데이터·동일한 템플릿을 쓴다. 수치가 어긋나면 그건 버그다.

## 시작

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d   # PostgreSQL+pgvector · Redmine · Ollama

cd backend  && ./gradlew bootRun
cd frontend && npm ci && npm run dev
```

## 규약 요약

```
커밋    <type>(<scope>): <제목>  [SWFR.PIP.010]
        Refs: GH-23, RM-204          ← 맨 #17 금지 (도구 구분 불가 + Redmine 오인식)
브랜치  feat/REQ-012-<slug> · main 직접 push 금지 · Squash merge
추적표  python scripts/build_traceability.py        (--check 로 규약 검증)
이슈    python scripts/github/gen_bootstrap.py …    → bash scripts/github/bootstrap.sh
```

요구사항 이슈는 손으로 만들지 않는다. **요구사항정의서가 단일 진실 원천**이고,
생성기가 그것을 GitHub 이슈로 옮긴다. 자세한 절차는
[`scripts/github/README.md`](./scripts/github/README.md).

## 마일스톤

| | | 목표일 |
|---|---|---|
| M0 | 착수보고 | 2026.08.11 ✅ |
| M1 | 범위·평가기준 확정 | 2026.08.29 |
| M2 | 연계·수집 기반 확보 | 2026.09.12 |
| M3 | 통합 현황 시연 (중간보고, 필요시·협의) | 2026.09.30 |
| M4 | 통합 PoC 완성 | 2026.10.23 |
| M5 | 최종보고 (통합 PoC 실증 완료) | 2026.11.13 |
| M6 | 최종 인도 | 2026.11.30 |
