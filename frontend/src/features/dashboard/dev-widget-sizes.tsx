import { type ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { resolveWidgetRenderer } from '@/features/widgets/renderer-registry';
import { sampleInfographic } from '@/features/ax-query/viz-preview';
import { label } from '@/lib/labels';
import type { WidgetSpec, WidgetTemplate } from '@/types/api';

/**
 * 개발용 자 — 위젯을 실제 그리드 칸 크기로 그려 놓고 최소 크기를 눈으로 잰다.
 * 대시보드와 같은 값(rowHeight 80 · margin 16 · 12칸)을 쓴다.
 */
const ROW_HEIGHT = 80;
const MARGIN = 16;
const CONTAINER = 1200;

const px = (w: number, h: number) => ({
  width: (CONTAINER - MARGIN * 13) * (w / 12) + MARGIN * (w - 1),
  height: h * ROW_HEIGHT + (h - 1) * MARGIN,
});

const TEMPLATES = [
  'STAT_CARD',
  'BAR_CHART',
  'LINE_CHART',
  'AREA_CHART',
  'STACKED_BAR_CHART',
  'HORIZONTAL_BAR_CHART',
  'PIE_CHART',
  'DONUT_CHART',
  'RADAR_CHART',
  'STATUS_FLOW',
  'HEATMAP',
  'PROGRESS_LIST',
  'DATA_TABLE',
  'CHECKLIST',
  'GANTT_SUMMARY',
] as const satisfies readonly WidgetTemplate[];

const CANDIDATES: [number, number][] = [
  [2, 2],
  [3, 2],
  [3, 3],
  [4, 3],
  [6, 4],
];

/** 미리보기 값은 채팅 인포그래픽과 같은 표본을 쓴다 — 실제로 그려질 모양과 같다. */
const sampleFor = (template: WidgetTemplate) => {
  const chatLike = sampleInfographic(
    (
      ['STAT_CARD', 'PROGRESS_LIST', 'DATA_TABLE', 'CHECKLIST', 'GANTT_SUMMARY'] as string[]
    ).includes(template)
      ? 'BAR_CHART'
      : template,
  );
  return chatLike.data;
};

const specFor = (template: WidgetTemplate): WidgetSpec => ({
  template,
  title: label(template),
  query: null as unknown as WidgetSpec['query'],
  options: null,
});

export function DevWidgetSizes(): ReactNode {
  return (
    <div className="bg-background min-h-screen p-6">
      <h1 className="text-lg font-semibold">위젯 최소 크기 자</h1>
      <p className="text-muted-foreground mb-6 text-sm">
        칸 크기(w×h)별 실제 렌더. 제목·축·범례가 잘리기 시작하는 칸이 그 템플릿의 바닥이다.
      </p>
      {TEMPLATES.map((template) => {
        const Renderer = resolveWidgetRenderer(template);
        const data = sampleFor(template);
        const spec = specFor(template);
        return (
          <section key={template} className="mb-10" data-template={template}>
            <h2 className="mb-2 font-mono text-sm font-semibold">
              {template} · {label(template)}
            </h2>
            <div className="flex flex-wrap items-start gap-4">
              {CANDIDATES.map(([w, h]) => (
                <div key={`${w}x${h}`} style={px(w, h)} className="shrink-0">
                  <p className="text-muted-foreground mb-1 font-mono text-[10px]">
                    {w}×{h}
                  </p>
                  <Card className="flex h-full flex-col overflow-hidden">
                    <CardHeader className="shrink-0">
                      <CardTitle className="truncate text-sm">{spec.title}</CardTitle>
                    </CardHeader>
                    <CardContent className="min-h-0 flex-1 overflow-hidden">
                      <Renderer spec={spec} data={data} />
                    </CardContent>
                  </Card>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
