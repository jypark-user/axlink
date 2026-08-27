import { describe, expect, it } from 'vitest';
import {
  defaultGridItem,
  toDashboardLayout,
  toGridLayouts,
  DEFAULT_SIZE,
  fillMissing,
  MIN_COLS,
} from '@/features/dashboard/layout-mapper';
import type { DashboardLayout } from '@/types/api';

const layout: DashboardLayout = {
  lg: [{ i: 'a', x: 0, y: 0, w: 6, h: 4, minW: 3, minH: 3 }],
  md: [{ i: 'a', x: 0, y: 0, w: 4, h: 4, minW: null, minH: null }],
  sm: [],
};

describe('layout-mapper', () => {
  it('drops null minW/minH instead of forwarding null to react-grid-layout', () => {
    const grid = toGridLayouts(layout);
    expect(grid.lg[0]).toMatchObject({ minW: 3, minH: 3 });
    expect('minW' in grid.md[0]).toBe(false);
  });

  it('omits empty breakpoints so rgl derives them from lg instead of shrinking widgets to 1x1', () => {
    const grid = toGridLayouts(layout);
    expect('sm' in grid).toBe(false);
    expect('md' in grid).toBe(true);
  });

  it('round-trips back to the server contract without rgl extra fields', () => {
    const back = toDashboardLayout({
      lg: [{ i: 'a', x: 0, y: 0, w: 6, h: 4, minW: 3, minH: 3, static: true, moved: true }],
      md: [{ i: 'a', x: 0, y: 0, w: 4, h: 4 }],
      sm: [],
    });
    expect(back).toEqual(layout);
    expect(Object.keys(back.lg[0]).sort()).toEqual(['h', 'i', 'minH', 'minW', 'w', 'x', 'y']);
  });

  it('stacks a new widget below the tallest existing item', () => {
    const item = defaultGridItem('new', 'DATA_TABLE', layout.lg);
    const size = DEFAULT_SIZE.DATA_TABLE;
    expect(item).toEqual({
      i: 'new',
      x: 0,
      y: 4,
      w: size.w,
      h: size.h,
      minW: size.minW,
      minH: size.minH,
    });
  });
});

describe('fillMissing', () => {
  const widgets = [
    { id: 'a', template: 'BAR_CHART' as const },
    { id: 'b', template: 'LINE_CHART' as const },
    { id: 'c', template: 'STAT_CARD' as const },
  ];

  it('자리가 다 있으면 레이아웃을 그대로 둔다', () => {
    const full: DashboardLayout = {
      lg: widgets.map((w, i) => ({ i: w.id, x: i * 3, y: 0, w: 3, h: 3, minW: 3, minH: 3 })),
      md: [],
      sm: [],
    };
    expect(fillMissing(full, widgets)).toBe(full);
  });

  it('빠진 위젯을 가로로 흘려 담는다 — 한 줄에 12칸까지', () => {
    const filled = fillMissing({ lg: [], md: [], sm: [] }, widgets);
    const [a, b, c] = filled.lg;
    // 막대 6 + 라인 6 = 12 → 같은 줄, 숫자 카드는 다음 줄
    expect([a.x, a.y]).toEqual([0, 0]);
    expect([b.x, b.y]).toEqual([6, 0]);
    expect([c.x, c.y]).toEqual([0, 4]);
  });

  it('이미 놓인 것 아래에서 시작한다', () => {
    const existing: DashboardLayout = {
      lg: [{ i: 'z', x: 0, y: 0, w: 6, h: 5, minW: 3, minH: 3 }],
      md: [],
      sm: [],
    };
    const filled = fillMissing(existing, widgets);
    expect(filled.lg).toHaveLength(4);
    expect(filled.lg.slice(1).every((g) => g.y >= 5)).toBe(true);
  });
});

describe('DEFAULT_SIZE', () => {
  it('12칸 그리드에서 최소 폭은 3칸 아래로 내려가지 않는다', () => {
    for (const [template, size] of Object.entries(DEFAULT_SIZE)) {
      expect(size.minW, template).toBeGreaterThanOrEqual(MIN_COLS);
      // 기본 크기가 최소보다 작으면 놓자마자 규칙을 어긴다.
      expect(size.w, template).toBeGreaterThanOrEqual(size.minW);
      expect(size.h, template).toBeGreaterThanOrEqual(size.minH);
      expect(size.w, template).toBeLessThanOrEqual(12);
    }
  });
});

describe('fillMissing 최소 크기 보정', () => {
  const widgets = [{ id: 'a', template: 'BAR_CHART' as const }];

  it('최소보다 좁게 저장된 자리를 끌어올린다', () => {
    const narrow: DashboardLayout = {
      lg: [{ i: 'a', x: 10, y: 0, w: 2, h: 1, minW: null, minH: null }],
      md: [],
      sm: [],
    };
    const [item] = fillMissing(narrow, widgets).lg;
    const size = DEFAULT_SIZE.BAR_CHART;
    expect(item.w).toBe(size.minW);
    expect(item.h).toBe(size.minH);
    // 넓어진 만큼 오른쪽으로 넘치지 않게 x 를 당긴다.
    expect(item.x + item.w).toBeLessThanOrEqual(12);
  });

  it('이미 최소를 넘으면 손대지 않는다', () => {
    const wide: DashboardLayout = {
      lg: [{ i: 'a', x: 0, y: 0, w: 6, h: 4, minW: 3, minH: 3 }],
      md: [],
      sm: [],
    };
    expect(fillMissing(wide, widgets)).toBe(wide);
  });
});
