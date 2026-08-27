import type { SseInfographicEvent, WidgetColumn, WidgetTemplate } from '@/types/api';

/** 채팅에서 서버가 고를 수 있는 그림 10종. 큰 숫자 카드는 쓰지 않는다. */
export const CHAT_TEMPLATES: WidgetTemplate[] = [
  'LINE_CHART',
  'AREA_CHART',
  'BAR_CHART',
  'HORIZONTAL_BAR_CHART',
  'STACKED_BAR_CHART',
  'PIE_CHART',
  'DONUT_CHART',
  'RADAR_CHART',
  'STATUS_FLOW',
  'HEATMAP',
  'CUMULATIVE_FLOW',
  'PARETO',
  'TREEMAP',
  'SLOPE_CHART',
  'BUMP_CHART',
  'SPARKLINE',
  'BULLET_CHART',
  'CALENDAR_HEATMAP',
];

/** 달력용 날짜 축 — `2026-05-01` 처럼 서버 `period_day` 축과 같은 모양으로 만든다. */
const days = (n: number) =>
  Array.from({ length: n }, (_, i) =>
    new Date(Date.UTC(2026, 4, 1 + i)).toISOString().slice(0, 10),
  );

const col = (key: string, label: string, type: string): WidgetColumn => ({ key, label, type });

const ORGS = ['넥스트소프트', '한빛시스템', '대성ICT', '유니콘랩', '코어테크'];
const STATUSES = ['수집 안 됨', '초안', '제출', '승인'];
const ACTIVITIES = ['PM.1', 'PM.2', 'PM.3', 'PM.4', 'SI.1', 'SI.2', 'SI.3'];

/** 값이 바뀌면 그림도 바뀌어야 한다 — 씨앗을 넣어 매번 같은 수를 만든다. */
const at = (seed: number, max: number) => ((seed * 37 + 11) % max) + 1;

const months = (n: number) =>
  Array.from({ length: n }, (_, i) => `${((i % 12) + 1).toString().padStart(2, '0')}월`);

const oneDim = (
  labels: string[],
  dimLabel: string,
  valueLabel: string,
  unit: string | null,
  timeAxis = false,
) => ({
  dimensions: ['d0'],
  columns: [col('d0', dimLabel, timeAxis ? 'date' : 'string'), col('value', valueLabel, 'number')],
  rows: labels.map((name, i) => ({ values: { d0: name, value: at(i, unit === '%' ? 100 : 40) } })),
  unit,
});

const twoDim = (xs: string[], series: string[]) => ({
  dimensions: ['d0', 'd1'],
  columns: [
    col('d0', '기간', 'string'),
    col('d1', '용역사', 'string'),
    col('value', '건수', 'number'),
  ],
  rows: xs.flatMap((x, i) =>
    series.map((s, j) => ({ values: { d0: x, d1: s, value: at(i * 7 + j, 30) } })),
  ),
  unit: '건',
});

/** 템플릿마다 그 그림이 쓰일 법한 모양의 값을 만든다. */
export function sampleInfographic(template: WidgetTemplate): SseInfographicEvent {
  const shape =
    template === 'LINE_CHART'
      ? oneDim(months(6), '월', '미결 이슈', '건', true)
      : template === 'AREA_CHART'
        ? oneDim(months(18), '월', '누적 이슈', '건', true)
        : template === 'BAR_CHART'
          ? oneDim(ORGS.slice(0, 5), '용역사', '미결 이슈', '건')
          : template === 'HORIZONTAL_BAR_CHART'
            ? oneDim(
                Array.from({ length: 14 }, (_, i) => `요구사항 REQ-${100 + i}`),
                '요구사항',
                '연결된 이슈',
                '건',
              )
            : template === 'PIE_CHART'
              ? oneDim(ORGS.slice(0, 3), '용역사', '비중', '건')
              : template === 'DONUT_CHART'
                ? oneDim(ORGS, '용역사', '비중', '건')
                : template === 'RADAR_CHART'
                  ? oneDim(ACTIVITIES.slice(0, 6), '활동', '이행률', '%')
                  : template === 'STATUS_FLOW'
                    ? oneDim(STATUSES, '상태', '산출물', '건')
                    : template === 'HEATMAP'
                      ? twoDim(ACTIVITIES, ORGS.slice(0, 4))
                      : template === 'CUMULATIVE_FLOW'
                        ? twoDim(months(8), STATUSES)
                        : template === 'PARETO'
                          ? oneDim(ORGS, '용역사', '열린 이슈', '건')
                          : template === 'TREEMAP'
                            ? oneDim(
                                Array.from({ length: 18 }, (_, i) => `산출물 ${i + 1}`),
                                '산출물',
                                '미제출',
                                '건',
                              )
                            : template === 'SLOPE_CHART'
                              ? twoDim(months(2), ORGS.slice(0, 4))
                              : template === 'BUMP_CHART'
                                ? twoDim(months(5), ORGS.slice(0, 4))
                                : template === 'SPARKLINE'
                                  ? twoDim(months(6), ORGS.slice(0, 4))
                                  : template === 'BULLET_CHART'
                                    ? oneDim(ORGS.slice(0, 4), '용역사', '이행률', '%')
                                    : template === 'CALENDAR_HEATMAP'
                                      ? oneDim(days(35), '일', '커밋·MR', '건', true)
                                      : twoDim(months(4), ORGS.slice(0, 3));

  return {
    template,
    title: `[미리보기] ${template}`,
    data: {
      measure: 'preview',
      measureLabel: `[미리보기] ${template}`,
      unit: shape.unit,
      dimensions: shape.dimensions,
      columns: shape.columns,
      rows: shape.rows,
      total: null,
      previousTotal: null,
      // 불릿은 목표선이 있어야 그림이 성립한다 — 미리보기에서도 하나 준다.
      target: template === 'BULLET_CHART' ? 90 : null,
      appliedProjectIds: [],
      truncated: false,
      generatedAt: new Date().toISOString(),
    },
  };
}

/**
 * 개발 빌드에서만 콘솔에 도구를 붙인다.
 *   axViz()              다음 그림으로 넘김
 *   axViz('PIE_CHART')   그 그림으로 바꿈
 *   axViz(null)          미리보기 끔
 */
export function registerVizPreview(set: (e: SseInfographicEvent | null) => void): () => void {
  if (!import.meta.env.DEV) return () => undefined;
  let cursor = -1;
  const api = (template?: WidgetTemplate | null) => {
    if (template === null) {
      set(null);
      return '미리보기 끔';
    }
    if (template === undefined) {
      cursor = (cursor + 1) % CHAT_TEMPLATES.length;
    } else {
      cursor = CHAT_TEMPLATES.indexOf(template);
      if (cursor < 0) return `모르는 템플릿: ${template} · ${CHAT_TEMPLATES.join(', ')}`;
    }
    const picked = CHAT_TEMPLATES[cursor];
    set(sampleInfographic(picked));
    return `${cursor + 1}/${CHAT_TEMPLATES.length} ${picked}`;
  };
  (window as unknown as Record<string, unknown>).axViz = api;
  (window as unknown as Record<string, unknown>).axVizList = CHAT_TEMPLATES;
  return () => {
    delete (window as unknown as Record<string, unknown>).axViz;
  };
}
