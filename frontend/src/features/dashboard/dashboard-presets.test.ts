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
      }
    }
  });

  it('모든 프리셋이 12컬럼 안에서 겹치지 않게 배치된다', () => {
    for (const preset of DASHBOARD_PRESETS) {
      const grid = packGrid(preset.widgets);
      expect(grid).toHaveLength(preset.widgets.length);
      grid.forEach((item, i) => {
        expect(item.x + item.w).toBeLessThanOrEqual(12);
        expect(item.w).toBe(DEFAULT_SIZE[preset.widgets[i].template].w);
        grid.slice(i + 1).forEach((other) => expect(overlaps(item, other)).toBe(false));
      });
    }
  });

  it('기존 위젯 아래에서 시작한다', () => {
    const grid = packGrid(DASHBOARD_PRESETS[0].widgets, 8);
    expect(Math.min(...grid.map((g) => g.y))).toBe(8);
  });

  it('spec 은 선택한 프로젝트 범위로만 조회한다', () => {
    const spec = toWidgetSpec(DASHBOARD_PRESETS[0].widgets[0], 'prj-1');
    expect(spec.query.projectScope).toEqual(['prj-1']);
    expect(spec.query.filters).toEqual([]);
  });
});
