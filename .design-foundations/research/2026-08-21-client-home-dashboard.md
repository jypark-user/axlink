# 발주사 메인 대시보드 — 설계 브리프

발주사(CLIENT) 계정이 로그인 직후 만나는 홈 화면으로, 감독 중인 사업 전부의 상태를 한 화면에서 브리핑한다.

- 날짜: 2026-08-21
- 상태: **draft**
- 다음 단계: `/design-for-ai:plan .design-foundations/research/2026-08-21-client-home-dashboard.md`

---

## 무엇을 만드는가

ax-link 는 발주사가 여러 SI 사업의 진행·산출물·시정조치·자료 수집 상태를 감독하는 웹앱이다. 지금 발주사가 로그인하면 `/projects` 목록으로 떨어진다 — 사업 이름과 몇 개 배지가 있을 뿐, "지금 내 사업들이 어떤 상태인가"는 사업을 하나씩 열어봐야 안다.

이 화면은 그 질문에 한 번에 답한다. **경보판이 아니라 현황 브리핑**이다. 무엇이 잘못됐는지 찾아주는 것보다, 전체가 어떻게 굴러가는지 보여주는 것이 먼저다. 경보는 그 안에서 색으로 튄다.

## 누가, 어떤 맥락에서

- **주 사용자**: 발주사(CLIENT) 담당자 — 사업을 직접 수행하지 않고 감독한다. 검수·승인·종료의 결정권자.
- **감독 규모**: 한 발주사가 동시에 보는 사업 **1~5개**. 한 화면에 모두 펼칠 수 있는 규모이며, 검색·필터·페이징이 필요한 규모가 아니다.
- **기기**: 데스크톱 우선(업무용 브라우저). 태블릿까지 무리 없이, 휴대폰은 읽기 수준.
- **맥락**: 업무 시작 시점의 확인, 또는 회의 직전 브리핑. 오래 머무는 화면이 아니라 **훑고 사업으로 들어가는** 화면.

## 하려는 일 (JTBD)

> "내가 맡은 사업들이 지금 어떤 상태인지 한 번에 보고, 손봐야 할 곳으로 바로 들어가고 싶다."

지금은 이렇게 한다: `/projects` 목록을 열고 → 사업을 하나씩 클릭해 → 진행 상황·산출물·시정조치를 각각 확인한다. 사업이 3개면 최소 9번의 화면 이동이다. 그래서 실제로는 잘 확인하지 않게 되고, 문제는 용역사가 보고할 때 알게 된다.

## 화면이 해야 할 일 (우선순위 순)

1. 전체 현황을 **숫자 넷**으로 요약한다 — 상황·성적·행동·신뢰도.
2. 사업별로 **한 장씩** 상태를 보여준다 — 계획 대비 진척, 필수 산출물 승인, 열린 시정조치·리스크, 자료 신선도.
3. 문제 있는 사업은 카드 안에서 **색으로 튀게** 한다(별도 경보 영역을 두지 않는다).
4. 카드에서 해당 사업의 화면으로 **바로 들어간다**.

## 정해진 것

| 항목 | 결정 |
|---|---|
| 경로 | `/` (로그인 후 첫 화면). 발주사 기준. |
| 상단 요약 | **4칸** — 진행 중 사업 수 · 필수 산출물 승인률 · 열린 시정조치(지연 건수 포함) · 자료 신선도(마지막 수집, 실패 건수) |
| 본문 | 사업 카드 목록(사업당 한 장). 1~5개를 전부 펼친다. |
| 메뉴 | 사이드바 최상단에 **'홈' 추가**, 기존 '프로젝트' 목록은 **그대로 유지** |
| AI 질문 입력칸 | **두지 않는다**. 질문은 사이드바 '새 질문'으로만. |
| 데이터 | **`GET /api/overview` 신설**. 화면 진입 시 1회 호출. |
| 시각 언어 | ax-pms 와 동일 — 이미 ax-link 에 이식된 토큰·타이포·`Window`/`Tile`/`PageHeader` 프리미티브를 그대로 쓴다. 새 시각 언어를 만들지 않는다. |

## 데이터 — 지금 있는 것과 새로 필요한 것

**이미 있는 것 (사업 단위 호출)**

- `ProjectSummaryResponse` — `status`, `startDate`/`endDate`, `requiredWorkProductApproved`/`Total`, `openCorrectionActionCount`, `openRiskCount`, `updatedAt`
- `ProjectMetrics`(사업 상세) — `requirementAccepted`/`Total`, `issueOpen`, `riskOpen`, `workProductApproved`/`Total`, `traceabilityCoverage`, `lastSyncedAt`
- `ProgressRecordResponse` — `period`, `plannedPct`, `actualPct` ← **계획 대비 지연을 말할 수 있는 유일한 데이터**
- `CorrectionActionResponse` — `dueDate`, `overdueDays`, `status`
- `GET /sync-jobs` — 프로젝트 지정 없이 전 사업 조회 가능(실패 건 필터 가능)

**없는 것**: 전 사업을 가로지르는 통합 목록(기한 임박 시정조치, 최근 업로드 자료, 사업별 최신 진척)을 한 번에 주는 엔드포인트.

**신설 API 초안** — `GET /api/overview` (발주사 조직 범위로 스코프)

```
{
  projects: [{
    projectId, name, status, startDate, endDate,
    progress: { plannedPct, actualPct, period } | null,   // 최신 progress_record
    requiredWorkProduct: { approved, total },
    openCorrectionActions: number,
    overdueCorrectionActions: number,
    openRisks: number,
    lastSyncedAt, syncFailureCount
  }],
  totals: { activeProjects, totalProjects,
            approvedWorkProducts, totalWorkProducts,
            openCorrectionActions, overdueCorrectionActions,
            lastSyncedAt, syncFailureCount }
}
```

호출 1회로 화면 전체를 채우는 것이 목표다. 사업별 N회 호출은 하지 않는다.

## 하지 않는 것

- 위젯 편집·배치 변경 — 사업별 `/p/:id/dashboard` 가 이미 그 역할을 한다. 홈은 고정 배치.
- 차트 — 진척은 막대/비율 표시로 충분하다. 그래프가 필요해지면 사업 대시보드로 보낸다.
- 용역사(CONTRACTOR)·관리자(SUPER_ADMIN) 전용 홈 — 이번 범위 밖. 다만 카드 구성은 역할별로 갈라질 수 있게 둔다.
- 알림·읽음 상태 관리.

## Taste signals

- ax-pms 의 절제된 톤 — 옅은 바탕에 상태색은 글자에만(`bg-success-muted text-success` 식 배지), 큰 색 덩어리 금지.
- 숫자는 `tnum`(고정폭). 지표는 크게, 라벨은 `win-label`로 작게.
- 여백으로 구분하고 선은 최소로. ax-pms `Window`/`Tile` 의 카드 리듬을 따른다.
- 한국어 문장은 짧고 평서형. "지금 손봐야 할 일" 같은 구어체 헤딩 대신 "시정조치", "자료 수집" 같은 업무 용어를 그대로 쓴다.

## 열린 질문

1. **지연 판정 기준** — `actualPct < plannedPct` 이면 지연인가, 몇 %p 이상 벌어져야 지연인가? (기획 단계에서 확정 필요)
2. **progress_record 가 없는 사업**의 카드는 진척 자리를 무엇으로 채우는가? (기간 경과율? 빈 상태?)
3. **자료 신선도의 기준선** — 마지막 수집이 며칠 지나면 경고색인가?
4. 사업이 **0개**인 발주사(갓 가입)의 빈 화면은 무엇을 보여주는가?
5. 사업이 **5개를 넘는** 발주사가 생기면 카드 목록을 어떻게 접는가? (더 보기 / 표 전환)
6. 홈 진입 시 **CONTRACTOR·SUPER_ADMIN** 은 어디로 보내는가? (기존 `/projects` 유지 가정)
