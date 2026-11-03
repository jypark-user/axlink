import { describe, expect, it } from 'vitest';
import { DASHBOARD_PRESETS, packGrid, toWidgetSpec } from '@/features/dashboard/dashboard-presets';
import { DEFAULT_SIZE } from '@/features/dashboard/layout-mapper';
import { widgetRenderers } from '@/features/widgets/renderer-registry';

const overlaps = (
  a: { x: number; y: number; w: number; h: number },
  b: { x: number; y: number; w: number; h: number },
): boolean => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

describe('dashboard-presets', () => {
  it('프리셋 id 는 유일하고 위젯은 렌더러가 있는 템플릿만 쓴다', () => {
    const ids = DASHBOARD_PRESETS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const preset of DASHBOARD_PRESETS) {
      expect(preset.widgets.length).toBeGreaterThan(0);
      for (const w of preset.widgets) {
        expect(widgetRenderers[w.template]).toBeTypeOf('function');
        expect(w.intent.length).toBeGreaterThan(5);
      }
    }
  });

  // 진척률·일정·품질·리스크·산출물을 한 화면에서 본다 (SWFR.WEB.001). 추천 구성 「전체 진행 현황」이 그 화면이다
  it('전체 진행 현황은 다섯 축을 모두 담는다', () => {
    const overview = DASHBOARD_PRESETS.find((p) => p.id === 'overview');
    expect(overview).toBeDefined();
    const measures = new Set(overview!.widgets.map((w) => w.measure));
    const axes = {
      진척률: 'progress_representative_pct',
      일정: 'schedule_variance_pct',
      품질: 'issue_resolution_rate',
      리스크: 'open_risk_count',
      산출물: 'work_product_approval_rate',
    };
    for (const [axis, measure] of Object.entries(axes)) {
      expect(measures.has(measure), `${axis} 축(${measure})이 없다`).toBe(true);
    }
  });

  it('모든 프리셋이 12컬럼 안에서 겹치지 않게 배치된다', () => {
    for (const preset of DASHBOARD_PRESETS) {
      const grid = packGrid(preset.widgets);
      expect(grid).toHaveLength(preset.widgets.length);
      grid.forEach((item, i) => {
        expect(item.x + item.w).toBeLessThanOrEqual(12);
        expect(item.w).toBeGreaterThanOrEqual(DEFAULT_SIZE[preset.widgets[i].template].w);
        expect(item.h).toBeGreaterThanOrEqual(DEFAULT_SIZE[preset.widgets[i].template].h);
        grid.slice(i + 1).forEach((other) => expect(overlaps(item, other)).toBe(false));
      });
    }
  });

  it('마지막 줄을 빼고는 줄마다 12컬럼을 꽉 채우고 높이를 맞춘다', () => {
    for (const preset of DASHBOARD_PRESETS) {
      const grid = packGrid(preset.widgets);
      const rows = new Map<number, typeof grid>();
      for (const item of grid) rows.set(item.y, [...(rows.get(item.y) ?? []), item]);
      const ys = [...rows.keys()].sort((a, b) => a - b);
      ys.forEach((y, r) => {
        const items = rows.get(y)!;
        const width = items.reduce((sum, it) => sum + it.w, 0);
        if (r < ys.length - 1) expect(width).toBe(12);
        expect(new Set(items.map((it) => it.h)).size).toBe(1);
      });
    }
  });

  it('남은 칸은 한 칸씩 돌아가며 나누고 마지막 줄의 원형 차트는 6까지만 넓힌다', () => {
    const grid = packGrid([
      { template: 'STAT_CARD', title: 'a', intent: 'a', measure: 'm' },
      { template: 'STACKED_BAR_CHART', title: 'b', intent: 'b', measure: 'm' },
      { template: 'RADAR_CHART', title: 'c', intent: 'c', measure: 'm' },
      { template: 'DONUT_CHART', title: 'd', intent: 'd', measure: 'm' },
      { template: 'DONUT_CHART', title: 'e', intent: 'e', measure: 'm' },
    ]);
    // 3+6=9 → 남은 3칸을 번갈아: 카드 4(상한) · 막대 8. 높이는 막대 4에 맞춘다
    expect(grid.slice(0, 2).map((g) => [g.x, g.w, g.h])).toEqual([
      [0, 4, 4],
      [4, 8, 4],
    ]);
    // 마지막 줄 4+4+4=12 는 그대로다
    expect(grid.slice(2).map((g) => g.w)).toEqual([4, 4, 4]);
    const lone = packGrid([{ template: 'DONUT_CHART', title: 'd', intent: 'd', measure: 'm' }]);
    expect(lone[0].w).toBe(6);
  });

  it('기존 위젯 아래에서 시작한다', () => {
    const grid = packGrid(DASHBOARD_PRESETS[0].widgets, 8);
    expect(Math.min(...grid.map((g) => g.y))).toBe(8);
  });

  it('spec 은 선택한 프로젝트 범위로만 조회한다', () => {
    const spec = toWidgetSpec(DASHBOARD_PRESETS[0].widgets[0], 'prj-1');
    expect(spec.query.projectScope).toEqual(['prj-1']);
    expect(spec.query.filters).toEqual([]);
    expect(spec.prompt).toBe(DASHBOARD_PRESETS[0].widgets[0].intent);
  });
});
