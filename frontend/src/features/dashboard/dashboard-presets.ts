import { DEFAULT_SIZE } from '@/features/dashboard/layout-mapper';
import type { GridItem, WidgetSpec, WidgetTemplate } from '@/types/api';

/**
 * 진행 상황 추천 구성 — 위젯 여러 개를 한 번에 배치하는 사전 구성.
 * 위젯은 코드가 아니라 데이터(spec)이므로 여기서는 명세만 정의하고
 * 검증은 서버 시맨틱 카탈로그(measure/dimension)가 한다.
 */
export interface PresetWidget {
  template: WidgetTemplate;
  title: string;
  /** 사람이 "표시할 내용" 에 적었을 문장. 위젯 명세의 prompt 로 저장돼 고칠 때 보인다 */
  intent: string;
  measure: string;
  dimensions?: string[];
}

export interface DashboardPreset {
  id: string;
  name: string;
  description: string;
  widgets: PresetWidget[];
}

/**
 * 셋은 보는 목적이 달라서 그리는 방식도 달라야 한다.
 * 숫자 카드만 늘어놓은 화면을 세 개 주면 고를 이유가 없다.
 *   · 전체 진행 현황  — 지표판: 핵심 수치 석 장 + 장기 추이 + 구성비
 *   · 이슈 · 위험     — 분포판: 어디에 몰렸는지(누적) · 누가 막혔는지(순위) · 고른지(방사형)
 *   · 산출물 · 요구사항 — 점검판: 22종을 하나씩 짚고, 활동 × 유형 격자로 구멍을 찾는다
 *
 * 템플릿은 데이터 모양에 맞춰 고른다 — 채팅 인포그래픽과 같은 기준이다.
 *   시간축 12구간 이하 선 · 초과 면적 / 범주 3 이하 원 · 6 이하 도넛 · 12 이하 막대 ·
 *   초과 가로 막대 / 축 2개 누적 막대(칸 40 이하)·격자(초과) / 비율 8개 이하 방사형
 * measure × dimension 은 서버 시맨틱 카탈로그가 허용한 짝만 쓴다.
 */
export const DASHBOARD_PRESETS: DashboardPreset[] = [
  {
    id: 'full',
    name: '전체 인포템플릿',
    description: '그릴 수 있는 위젯 전부를 한 판에 — 어떤 그림이 있는지 훑어보고 골라내는 용도.',
    // GANTT_SUMMARY 만 뺐다 — planned/actual 컬럼을 요구하는데 시맨틱 집계는 그 모양을 못 만든다.
    widgets: [
      // ① 지금 위치 — 숫자·목표선·잔추세
      {
        template: 'STAT_CARD',
        title: '일정 진척(계획 대비)',
        intent: '이번 달 실적 진척률이 계획보다 얼마나 앞서거나 뒤졌는지 한 숫자로',
        measure: 'schedule_variance_pct',
        dimensions: ['period_month'],
      },
      {
        template: 'BULLET_CHART',
        title: '용역사별 일반 이슈 처리율 vs 목표',
        intent: '용역사별 이슈 처리율을 목표선(85%)과 나란히 보여줘',
        measure: 'issue_resolution_rate',
        dimensions: ['contractor_org'],
      },
      {
        template: 'SPARKLINE',
        title: '상태별 일반 이슈 잔추세',
        intent: '월별로 상태별 이슈 건수가 어떻게 남아 있는지 작은 추세선으로',
        measure: 'issue_count',
        dimensions: ['period_month', 'issue_status'],
      },
      // ② 흐름 — 시간이 지나며 어떻게 변하나
      {
        template: 'LINE_CHART',
        title: '월별 시험 통과율',
        intent: '월별 CI 시험 통과율 추이',
        measure: 'test_pass_rate',
        dimensions: ['period_month'],
      },
      {
        template: 'AREA_CHART',
        title: '주별 일반 이슈 처리율 추이',
        intent: '주별 이슈 처리율이 오르고 있는지 내리고 있는지',
        measure: 'issue_resolution_rate',
        dimensions: ['period_week'],
      },
      {
        template: 'CUMULATIVE_FLOW',
        title: '일반 이슈 누적 흐름(쌓임 vs 닫힘)',
        intent: '월별로 이슈가 쌓이는 속도와 닫히는 속도를 누적 흐름으로',
        measure: 'issue_count',
        dimensions: ['period_month', 'issue_status'],
      },
      {
        template: 'CALENDAR_HEATMAP',
        title: '일별 커밋·MR 활동',
        intent: '날짜별 커밋과 머지리퀘스트 활동량을 달력 히트맵으로',
        measure: 'code_activity_count',
        dimensions: ['period_day'],
      },
      // ③ 분포 — 어디에 몰렸나
      {
        template: 'BAR_CHART',
        title: '심각도별 열린 일반 이슈',
        intent: '열린 이슈가 심각도별로 몇 건인지',
        measure: 'open_issue_count',
        dimensions: ['issue_severity'],
      },
      {
        template: 'PARETO',
        title: '담당자별 열린 일반 이슈 집중도',
        intent: '열린 이슈가 어느 담당자에게 몰려 있는지 파레토로',
        measure: 'open_issue_count',
        dimensions: ['assignee'],
      },
      {
        template: 'STACKED_BAR_CHART',
        title: '용역사 × 심각도별 일반 이슈',
        intent: '용역사별 이슈를 심각도로 쌓아서',
        measure: 'issue_count',
        dimensions: ['contractor_org', 'issue_severity'],
      },
      {
        template: 'HEATMAP',
        title: '활동 × 산출물 유형별 미제출',
        intent: '29110 활동과 산출물 유형별로 미제출이 어디에 몰려 있는지 히트맵으로',
        measure: 'work_product_missing_count',
        dimensions: ['iso_activity', 'work_product_type'],
      },
      {
        template: 'TREEMAP',
        title: '유형별 미제출 산출물 크기',
        intent: '미제출 산출물을 유형별 크기로 한눈에',
        measure: 'work_product_missing_count',
        dimensions: ['work_product_type'],
      },
      // ④ 구성 — 무엇으로 이뤄졌나
      {
        template: 'PIE_CHART',
        title: '상태별 열린 리스크',
        intent: '열린 리스크가 상태별로 몇 건인지',
        measure: 'open_risk_count',
        dimensions: ['risk_status'],
      },
      {
        template: 'DONUT_CHART',
        title: '우선순위별 요구사항 비중',
        intent: '요구사항 이행률을 우선순위별로 나눠 비중으로',
        measure: 'requirement_fulfillment_rate',
        dimensions: ['requirement_priority'],
      },
      {
        template: 'STATUS_FLOW',
        title: '요구사항 단계 분포',
        intent: '요구사항이 정의·구현·검증·인수 단계에 각각 몇 건 있는지 흐름으로',
        measure: 'requirement_fulfillment_rate',
        dimensions: ['requirement_status'],
      },
      {
        template: 'RADAR_CHART',
        title: '활동별 산출물 승인률 균형',
        intent: '29110 활동별 산출물 승인률이 고르게 가는지 레이더로',
        measure: 'work_product_approval_rate',
        dimensions: ['iso_activity'],
      },
      // ⑤ 변화 — 순위와 기울기
      {
        template: 'SLOPE_CHART',
        title: '용역사별 일반 이슈, 처음과 지금',
        intent: '용역사별 이슈 건수가 첫 달과 지금 사이에 어떻게 바뀌었는지',
        measure: 'issue_count',
        dimensions: ['period_month', 'contractor_org'],
      },
      {
        template: 'BUMP_CHART',
        title: '심각도별 일반 이슈 순위 변화',
        intent: '월별로 심각도별 이슈 건수 순위가 어떻게 바뀌는지',
        measure: 'issue_count',
        dimensions: ['period_month', 'issue_severity'],
      },
      // ⑥ 점검 — 하나씩 짚기
      {
        template: 'PROGRESS_LIST',
        title: '용역사별 요구사항 이행률',
        intent: '용역사별 요구사항 이행률을 진행 막대 목록으로',
        measure: 'requirement_fulfillment_rate',
        dimensions: ['contractor_org'],
      },
      {
        template: 'HORIZONTAL_BAR_CHART',
        title: '산출물 22종 승인률',
        intent: '산출물 22종 각각의 승인률을 가로 막대로',
        measure: 'work_product_approval_rate',
        dimensions: ['work_product_type'],
      },
      {
        template: 'CHECKLIST',
        title: '산출물 22종 승인 점검표',
        intent: '산출물 22종이 승인됐는지 점검표로 하나씩',
        measure: 'work_product_approval_rate',
        dimensions: ['work_product_type'],
      },
      {
        template: 'DATA_TABLE',
        title: '담당자별 일반 이슈 평균 처리일',
        intent: '담당자별로 이슈 하나를 닫는 데 평균 며칠 걸리는지 표로',
        measure: 'issue_avg_resolution_days',
        dimensions: ['assignee'],
      },
    ],
  },
  {
    id: 'overview',
    name: '전체 진행 현황',
    description:
      '진척·일정·품질·리스크·산출물 다섯 축을 한 판에. 핵심 수치로 지금 위치를 읽고, 추이와 구성비로 흐름을 본다. 보고용.',
    // 한 화면에 다섯 축(SWFR.WEB.001): 진척률 · 일정 · 품질 · 리스크 · 산출물. 카드 넷이 윗줄이다.
    widgets: [
      // 기간 축을 달아 카드 안에 추세선이 그려지게 한다 — 숫자만으로는 방향을 모른다.
      {
        template: 'STAT_CARD',
        title: '대표 진척률',
        intent: '가장 최근 스냅샷의 대표 진척률을 월별 추세와 함께 한 숫자로',
        measure: 'progress_representative_pct',
        dimensions: ['period_month'],
      },
      {
        template: 'STAT_CARD',
        title: '일정 진척(계획 대비)',
        intent: '이번 달 실적 진척률이 계획보다 얼마나 앞서거나 뒤졌는지 한 숫자로',
        measure: 'schedule_variance_pct',
        dimensions: ['period_month'],
      },
      {
        template: 'STAT_CARD',
        title: '요구사항 이행률',
        intent: '월별 요구사항 이행률의 현재 값과 목표',
        measure: 'requirement_fulfillment_rate',
        dimensions: ['period_month'],
      },
      {
        template: 'STAT_CARD',
        title: '산출물 승인률',
        intent: 'WBS 가 정한 산출물 중 현행 버전이 승인된 비율',
        measure: 'deliverable_approval_rate',
      },
      {
        template: 'STAT_CARD',
        title: '일정 준수율',
        intent: '기한이 지난 마일스톤 중 기한 안에 닫힌 비율. 계획 대비 편차와 다른 카드',
        measure: 'schedule_compliance_rate',
      },
      {
        template: 'STAT_CARD',
        title: '일반 이슈 처리율',
        intent: '해결·종료된 일반 이슈 비율을 월별 추세와 함께 한 숫자로',
        measure: 'issue_resolution_rate',
        dimensions: ['period_month'],
      },
      {
        template: 'BAR_CHART',
        title: '심각도별 열린 리스크',
        intent: '종료되지 않은 리스크가 심각도별로 몇 건인지',
        measure: 'open_risk_count',
        dimensions: ['risk_severity'],
      },
      // 월이 쌓이면 선이 빽빽해진다 — 면적이 흐름을 더 잘 보여 준다.
      {
        template: 'AREA_CHART',
        title: '월별 요구사항 이행률 추이',
        intent: '월별 요구사항 이행률이 어떻게 올라왔는지 면적 추이로',
        measure: 'requirement_fulfillment_rate',
        dimensions: ['period_month'],
      },
      {
        template: 'STATUS_FLOW',
        title: '요구사항 단계 분포',
        intent: '요구사항이 정의·구현·검증·인수 단계에 각각 몇 건 있는지 흐름으로',
        measure: 'requirement_fulfillment_rate',
        dimensions: ['requirement_status'],
      },
      // MoSCoW 넷 — 원보다 도넛이 가운데에 합계를 둘 수 있어 낫다.
      {
        template: 'DONUT_CHART',
        title: '우선순위별 요구사항 비중',
        intent: '요구사항 이행률을 우선순위별로 나눠 비중으로',
        measure: 'requirement_fulfillment_rate',
        dimensions: ['requirement_priority'],
      },
    ],
  },
  {
    id: 'issue',
    name: '이슈 · 위험 중심',
    description: '어디에 몰려 있고 누가 막혀 있는지 — 분포·순위·균형으로 본다.',
    widgets: [
      {
        template: 'STAT_CARD',
        title: '일반 이슈 평균 처리일',
        intent: '이슈 하나를 닫는 데 평균 며칠 걸리는지',
        measure: 'issue_avg_resolution_days',
      },
      // 용역사 안에서 심각도가 어떻게 갈리는지 — 막대 둘로 나눠 보면 비교가 안 된다.
      {
        template: 'STACKED_BAR_CHART',
        title: '용역사 × 심각도별 열린 일반 이슈',
        intent: '용역사별 열린 이슈를 심각도로 쌓아서',
        measure: 'open_issue_count',
        dimensions: ['contractor_org', 'issue_severity'],
      },
      // 담당자는 수가 많다 — 세로 막대는 이름이 겹쳐 읽히지 않는다.
      {
        template: 'HORIZONTAL_BAR_CHART',
        title: '담당자별 열린 일반 이슈',
        intent: '담당자별 열린 이슈 건수를 가로 막대로',
        measure: 'open_issue_count',
        dimensions: ['assignee'],
      },
      {
        template: 'AREA_CHART',
        title: '주별 일반 이슈 처리율 추이',
        intent: '주별 이슈 처리율이 오르고 있는지 내리고 있는지',
        measure: 'issue_resolution_rate',
        dimensions: ['period_week'],
      },
      // 처리율이 한쪽만 낮으면 찌그러진 모양으로 바로 보인다.
      {
        template: 'RADAR_CHART',
        title: '용역사별 일반 이슈 처리율 균형',
        intent: '용역사별 이슈 처리율이 고른지 레이더로',
        measure: 'issue_resolution_rate',
        dimensions: ['contractor_org'],
      },
      {
        template: 'DONUT_CHART',
        title: '심각도별 열린 리스크',
        intent: '열린 리스크가 심각도별로 몇 건인지 도넛으로',
        measure: 'open_risk_count',
        dimensions: ['risk_severity'],
      },
    ],
  },
  {
    id: 'deliverable',
    name: '산출물 · 요구사항 중심',
    description: '받기로 한 것 중 무엇이 비었는지 — 점검표로 하나씩 짚는다.',
    widgets: [
      {
        template: 'STATUS_FLOW',
        title: '산출물 상태 분포',
        intent: '산출물이 미제출·제출·승인 상태에 각각 몇 건 있는지 흐름으로',
        measure: 'work_product_approval_rate',
        dimensions: ['work_product_status'],
      },
      {
        template: 'HEATMAP',
        title: '활동 × 산출물 유형별 미제출',
        intent: '29110 활동과 산출물 유형별로 미제출이 어디에 몰려 있는지 히트맵으로',
        measure: 'work_product_missing_count',
        dimensions: ['iso_activity', 'work_product_type'],
      },
      {
        template: 'CHECKLIST',
        title: '산출물 22종 승인 점검표',
        intent: '산출물 22종이 승인됐는지 점검표로 하나씩',
        measure: 'work_product_approval_rate',
        dimensions: ['work_product_type'],
      },
      // 22종은 세로 막대로 못 읽는다 — 눕히고 낮은 것부터 눈에 들어오게 한다.
      {
        template: 'HORIZONTAL_BAR_CHART',
        title: '산출물 22종 승인률',
        intent: '산출물 22종 각각의 승인률을 가로 막대로',
        measure: 'work_product_approval_rate',
        dimensions: ['work_product_type'],
      },
      // PM·SI 활동 10단계 — 어느 단계가 처지는지 균형으로 본다.
      {
        template: 'RADAR_CHART',
        title: '활동별 산출물 승인률 균형',
        intent: '29110 활동별 산출물 승인률이 고르게 가는지 레이더로',
        measure: 'work_product_approval_rate',
        dimensions: ['iso_activity'],
      },
      {
        template: 'STAT_CARD',
        title: '요구사항→시험 추적률',
        intent: '시험 케이스가 연결된 요구사항 비율 현재 값',
        measure: 'requirement_test_trace_rate',
      },
    ],
  },
];

export const toWidgetSpec = (widget: PresetWidget, projectId: string): WidgetSpec => ({
  template: widget.template,
  title: widget.title,
  prompt: widget.intent,
  query: {
    measure: widget.measure,
    dimensions: widget.dimensions ?? [],
    filters: [],
    projectScope: [projectId],
    limit: null,
  },
  options: {
    unit: null,
    sort: 'desc',
    threshold: null,
    stacked: null,
    showLegend: null,
    compareWithPrevious: null,
    columns: null,
  },
});

/** 줄을 채울 때 더 넓어지지 않는 상한. 원형 차트와 숫자 카드는 넓어지면 비어 보인다. */
const STRETCH_MAX: Partial<Record<WidgetTemplate, number>> = {
  STAT_CARD: 4,
  PIE_CHART: 6,
  DONUT_CHART: 6,
  RADAR_CHART: 6,
};

/**
 * 위젯을 12컬럼 안에서 왼쪽→오른쪽으로 흘려 담는다. 서버가 i 를 위젯 id 로 채운다.
 *
 * 기본 폭대로만 놓으면 줄마다 오른쪽이 비고(3+6=9, 4+4=8) 옆 위젯보다 낮은 카드 밑에
 * 구멍이 남는다. 그래서 줄을 만든 뒤 남은 칸을 그 줄의 위젯에 한 칸씩 돌아가며 나눠 주고,
 * 한 줄의 높이는 가장 높은 위젯에 맞춘다. 글줄 맞춤처럼 마지막 줄만 왼쪽 정렬로 둔다.
 */
export const packGrid = (widgets: PresetWidget[], startY = 0, cols = 12): GridItem[] => {
  const rows: GridItem[][] = [];
  let row: GridItem[] = [];
  let used = 0;
  for (const w of widgets) {
    const size = DEFAULT_SIZE[w.template];
    if (used + size.w > cols && row.length > 0) {
      rows.push(row);
      row = [];
      used = 0;
    }
    row.push({ i: '', x: used, y: 0, w: size.w, h: size.h, minW: size.minW, minH: size.minH });
    used += size.w;
  }
  if (row.length > 0) rows.push(row);

  let y = startY;
  const out: GridItem[] = [];
  rows.forEach((items, r) => {
    const isLast = r === rows.length - 1;
    const templates = items.map((_, i) => widgets[out.length + i].template);
    let spare = cols - items.reduce((sum, it) => sum + it.w, 0);
    // 먼저 상한 안에서 나누고, 그래도 남으면(마지막 줄이 아닐 때만) 상한을 풀어 채운다.
    // 마지막 줄은 상한에서 멈춘다. 홀로 남은 도넛이 화면을 다 차지하지 않게
    const share = (capped: boolean) => {
      let guard = cols;
      while (spare > 0 && guard-- > 0) {
        let given = false;
        items.forEach((it, i) => {
          if (spare <= 0) return;
          const cap = capped ? (STRETCH_MAX[templates[i]] ?? cols) : cols;
          if (it.w < cap) {
            it.w += 1;
            spare -= 1;
            given = true;
          }
        });
        if (!given) break;
      }
    };
    share(true);
    if (!isLast) share(false);
    const height = Math.max(...items.map((it) => it.h));
    let x = 0;
    for (const it of items) {
      it.x = x;
      it.y = y;
      it.h = height;
      x += it.w;
      out.push(it);
    }
    y += height;
  });
  return out;
};
