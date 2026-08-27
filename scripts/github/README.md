# GitHub 저장소 부트스트랩

`jypark-user/axlink` 저장소에 라벨·마일스톤·이슈를 한 번에 등록한다.

## 왜 스크립트인가

Cowork 클라우드 컨테이너에서는 GitHub API가 차단되어 있다(502). 그리고 이슈 51건을
손으로 만들 수는 없다. 무엇보다 **요구사항정의서가 단일 진실 원천**이어야 하므로,
이슈를 사람이 쓰지 않고 문서에서 생성한다.

```
docs/10-requirements/IM-001-요구사항정의서.md   ← 여기만 고친다
        │  scripts/github/gen_bootstrap.py
        ▼
scripts/github/bootstrap.sh                    ← 생성물. 직접 고치지 않는다
        │  gh CLI
        ▼
GitHub 이슈 51건
```

토큰은 `gh`의 자격증명 저장소에만 있다. 파일에도, 대화에도 남지 않는다.

## 1회 실행 절차

### ① gh CLI 설치 (없으면)

```powershell
winget install --id GitHub.cli
```

설치 후 터미널을 새로 연다.

### ② 로그인

```bash
gh auth login
```

`GitHub.com` → `HTTPS` → `Login with a web browser` 순으로 고른다.

### ③ 저장소 생성

```bash
cd "D:/AX Link"
gh repo create jypark-user/axlink --private --source=. --remote=origin
```

`--source=.` 는 현재 폴더를 그대로 올린다는 뜻이다. 아직 push 하지는 않는다.

### ④ 초기 커밋 · push

파일럿 코드가 시드로 들어와 있으므로 커밋을 두 개로 나눈다.
**파일럿 인수 시점이 이력에 남아야 나중에 "무엇이 우리 작업인지" 구분된다.**

```bash
git add backend frontend tools .design-foundations docs/90-pilot
git commit -m "feat(infra): 파일럿 ax-link-ui-base 를 구현 기반으로 인수  [chore]

수행기관 파일럿을 새 저장소의 시드로 삼는다. UI/UX·위젯 템플릿 23종·
시맨틱 레이어·커넥터 포트 구조를 승계한다.

Refs: docs/20-design/파일럿-대조표.md"

git add -A
git commit -m "docs(docs): M1 산출물 및 작업 규약 반영  [chore]

요구사항정의서 v0.4(41건) · M1 합의서 v0.2 · 작업계획 v0.2 ·
파일럿 대조표 · CLAUDE.md 계층 매핑 재작성"

git branch -M main
git push -u origin main
```

### ⑤ 부트스트랩 실행

```bash
bash scripts/github/bootstrap.sh
```

같은 이름이 이미 있으면 건너뛴다. **여러 번 실행해도 안전하다.**

### ⑥ 확인

```bash
gh issue list --repo jypark-user/axlink --limit 60
gh issue list --repo jypark-user/axlink --label "파일럿: 없음"
```

## 등록되는 것

| 구분 | 수 | 내용 |
|---|---|---|
| 마일스톤 | 7 | **M0~M6 — 착수보고자료 v1.0 「추진일정 및 마일스톤」 표 그대로** |
| 라벨 | 18 | 유형 4 · 파일럿 판정 5 · 검증방법 3 · 모듈 6 |
| 이슈 | 51 | 요구사항 41 + 조사·인수·문서 10 |

### 마일스톤

명칭 · 목표일 · 「산출·확인」 문구는 **착수보고자료를 그대로 옮긴 것이다.**
발주기관 자료와 대조되는 값이므로 임의로 바꾸지 않는다. 바꿔야 하면
`gen_bootstrap.py` 의 `MILESTONES` 를 고치고 그 근거를 커밋 메시지에 남긴다.

M0(착수보고, 08.11)은 이미 완료되었으므로 `closed` 상태로 만든다.
**일정 준수율(`SWFR.PIP.007`)의 분모가 7이 되고 달성 1건이 잡힌다** —
자기참조 데이터로서 실제 값이 나오려면 M0가 있어야 한다.

### 마일스톤별 이슈 배정

| | 이슈 | 성격 |
|---|---|---|
| M0 | 0 | 완료 (closed) |
| M1 | 1 | 파일럿 빌드·기동 확인 |
| M2 | 15 | 커넥터·표준모델·조사 |
| M3 | 19 | **A1 진척 산정 · A2 확인 요청 · A3 스냅샷 · 화면** |
| M4 | 13 | RAG · LLM · 보안 · 통합 시연 |
| M5 | 2 | 시험 · 사례 조사 |
| M6 | 1 | 산출물 인도 |

M3에 19건이 몰려 있다. 파일럿에 없는 대형 기능(A1~A3)이 전부 여기라서
계획상으로도 W4~W6이 최대 부하 구간이다.

### 라벨 활용

```bash
# 신규 개발이 필요한 것만
gh issue list --label "파일럿: 없음"

# 파일럿 구현을 확인만 하면 되는 것 (25건)
gh issue list --label "파일럿: 구현"

# 시연 대상 (M4 대본이 된다)
gh issue list --label "검증: D"
```

`파일럿: 구현` 25건은 **닫는 조건이 다르다.** 새로 만드는 게 아니라
동작을 확인하고 근거를 남기면 닫힌다.

## 요구사항이 바뀌면

1. `docs/10-requirements/IM-001-요구사항정의서.md` 를 고친다
2. `python scripts/github/gen_bootstrap.py docs/10-requirements/IM-001-요구사항정의서.md scripts/github/bootstrap.sh`
3. `bash scripts/github/bootstrap.sh` — 새로 생긴 것만 등록된다

**이미 만들어진 이슈의 본문은 갱신되지 않는다.** 요구사항 문구가 바뀌면
해당 이슈를 닫고 새로 만들거나, 본문을 손으로 맞춘다. PoC 규모에서는
문구 변경이 잦지 않을 것으로 본다.
