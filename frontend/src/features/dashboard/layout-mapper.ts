import type { Layout, Layouts } from 'react-grid-layout';
import type { DashboardLayout, GridItem, WidgetTemplate } from '@/types/api';

export type Breakpoint = 'lg' | 'md' | 'sm';

export const BREAKPOINTS: Breakpoint[] = ['lg', 'md', 'sm'];

/** 12칸 그리드에서 위젯이 차지할 수 있는 가장 좁은 폭. 이보다 좁으면 어떤 템플릿도 못 읽는다. */
export const MIN_COLS = 3;

/**
 * 칸 크기별 최소값. /dev/widget-sizes 에서 실제로 그려 보고 잰 값이다.
 * (rowHeight 80 · margin 16 · 12칸 기준 — 이보다 작으면 축·범례가 잘려 못 읽는다.)
 */
export const DEFAULT_SIZE: Record<
  WidgetTemplate,
  { w: number; h: number; minW: number; minH: number }
> = {
  // 값 한 줄 — 2칸 폭이면 숫자와 단위가 줄바꿈된다.
  STAT_CARD: { w: 3, h: 2, minW: 3, minH: 2 },
  // 축 그래프는 높이 2에서 x축 라벨이 통째로 잘린다.
  BAR_CHART: { w: 6, h: 4, minW: 3, minH: 3 },
  LINE_CHART: { w: 6, h: 4, minW: 3, minH: 3 },
  AREA_CHART: { w: 6, h: 4, minW: 3, minH: 3 },
  // 계열 범례까지 있어 높이 2면 x축·범례가 함께 사라진다.
  STACKED_BAR_CHART: { w: 6, h: 4, minW: 3, minH: 3 },
  // 폭 2면 라벨이 자리를 다 먹어 막대가 사라지고, 높이 3이면 항목이 잘린다.
  HORIZONTAL_BAR_CHART: { w: 6, h: 5, minW: 4, minH: 4 },
  // 범례가 빠지면 색이 무엇인지 알 수 없다 — 높이 3부터 범례가 나온다.
  PIE_CHART: { w: 4, h: 4, minW: 3, minH: 3 },
  DONUT_CHART: { w: 4, h: 4, minW: 3, minH: 3 },
  // 축이 방사형이라 아래쪽 라벨까지 담으려면 높이 4가 필요하다.
  RADAR_CHART: { w: 4, h: 4, minW: 4, minH: 4 },
  // 한 줄 띠 + 단계별 범례 — 높이 2면 단계 절반만 보인다.
  STATUS_FLOW: { w: 6, h: 3, minW: 3, minH: 3 },
  // 폭 3이면 열이 넘쳐 가로 스크롤이 생긴다.
  HEATMAP: { w: 6, h: 5, minW: 4, minH: 3 },
  PROGRESS_LIST: { w: 4, h: 4, minW: 3, minH: 3 },
  // 폭 2면 머리글이 잘리고, 높이 2면 한 줄밖에 안 남는다.
  DATA_TABLE: { w: 8, h: 5, minW: 3, minH: 3 },
  CHECKLIST: { w: 6, h: 6, minW: 3, minH: 3 },
  // 기간 축을 담으려면 넓어야 한다. 표본 데이터가 없어 기존 값을 그대로 둔다.
  GANTT_SUMMARY: { w: 12, h: 4, minW: 6, minH: 3 },
  // 기간 축 위에 상태 띠가 쌓인다 — 좁으면 띠 경계가 붙어 흐름이 안 보인다.
  CUMULATIVE_FLOW: { w: 8, h: 5, minW: 5, minH: 4 },
  // 막대 + 누적선 + 오른쪽 축까지 있어 폭이 좁으면 축 하나가 잘린다.
  PARETO: { w: 8, h: 5, minW: 5, minH: 4 },
  // 넓이로 크기를 보는 그림이라 정사각에 가까워야 칸이 읽힌다.
  TREEMAP: { w: 6, h: 5, minW: 4, minH: 4 },
  // 두 시점만 그리니 좁아도 되지만, 범례가 항목 수만큼 붙는다.
  SLOPE_CHART: { w: 4, h: 4, minW: 3, minH: 3 },
  BUMP_CHART: { w: 8, h: 4, minW: 5, minH: 3 },
  // 한 줄에 한 항목 — 폭보다 높이가 항목 수를 정한다.
  SPARKLINE: { w: 4, h: 4, minW: 3, minH: 2 },
  // 이름 + 막대 + 목표선 + 값이 한 줄에 들어가야 한다.
  BULLET_CHART: { w: 6, h: 4, minW: 4, minH: 2 },
  // 요일 7줄 격자에 주 수만큼 옆으로 늘어난다.
  CALENDAR_HEATMAP: { w: 8, h: 3, minW: 5, minH: 3 },
};

const toLayoutItem = (item: GridItem): Layout => {
  const next: Layout = { i: item.i, x: item.x, y: item.y, w: item.w, h: item.h };
  if (item.minW !== null && item.minW !== undefined) next.minW = item.minW;
  if (item.minH !== null && item.minH !== undefined) next.minH = item.minH;
  return next;
};

const toGridItem = (item: Layout): GridItem => ({
  i: item.i,
  x: item.x,
  y: item.y,
  w: item.w,
  h: item.h,
  minW: item.minW ?? null,
  minH: item.minH ?? null,
});

/**
 * 빈 브레이크포인트는 키째로 뺀다 — react-grid-layout 은 `layouts[bp]` 가 있는지만 보고,
 * 빈 배열도 "있다"로 쳐서 위젯을 전부 1x1 로 떨어뜨린다. 키가 없어야 lg 에서 파생한다.
 */
export const toGridLayouts = (layout: DashboardLayout): Layouts => {
  const grid: Layouts = {};
  for (const bp of BREAKPOINTS) {
    const items = layout[bp];
    if (items && items.length > 0) grid[bp] = items.map(toLayoutItem);
  }
  return grid;
};

export const toDashboardLayout = (layouts: Layouts): DashboardLayout => ({
  lg: (layouts.lg ?? []).map(toGridItem),
  md: (layouts.md ?? []).map(toGridItem),
  sm: (layouts.sm ?? []).map(toGridItem),
});

export const defaultGridItem = (
  id: string,
  template: WidgetTemplate,
  current: GridItem[],
): GridItem => {
  const size = DEFAULT_SIZE[template] ?? DEFAULT_SIZE.STAT_CARD;
  const y = current.reduce((max, g) => Math.max(max, g.y + g.h), 0);
  return { i: id, x: 0, y, w: size.w, h: size.h, minW: size.minW, minH: size.minH };
};

/**
 * 레이아웃에 자리가 없는 위젯의 자리를 채워 넣는다.
 *
 * react-grid-layout 은 자리를 못 찾은 자식을 1x1 로 떨어뜨린다. 자식마다 `data-grid` 를 주면
 * 막을 수 있지만 그건 저장된 레이아웃을 **덮어써서** 전부 한 줄로 쌓이게 만든다.
 * 라이브러리에는 빠짐없는 레이아웃을 넘기는 것이 맞다 — 자리 계산은 여기서 한 번만 한다.
 *
 * 채워 넣는 자리는 마지막 줄부터 왼쪽→오른쪽으로 흘려 담는다.
 */
export const fillMissing = (
  layout: DashboardLayout,
  widgets: { id: string; template: WidgetTemplate }[],
  cols = 12,
): DashboardLayout => {
  const byId = new Map(widgets.map((w) => [w.id, w.template]));
  // 최소 크기를 정하기 전에 저장된 자리는 그보다 좁을 수 있다 — 불러올 때 끌어올린다.
  // minW 는 크기 조절만 막을 뿐, 이미 저장된 값을 고쳐 주지는 않는다.
  const raw = layout.lg ?? [];
  const placed = raw.map((g) => {
    const size = DEFAULT_SIZE[byId.get(g.i) as WidgetTemplate] ?? DEFAULT_SIZE.STAT_CARD;
    const w = Math.min(cols, Math.max(g.w, size.minW));
    const h = Math.max(g.h, size.minH);
    if (w === g.w && h === g.h) return g;
    return { ...g, w, h, x: Math.min(g.x, cols - w), minW: size.minW, minH: size.minH };
  });
  const clamped = placed.some((g, i) => g !== raw[i]);

  const known = new Set(placed.map((g) => g.i));
  const missing = widgets.filter((w) => !known.has(w.id));
  if (missing.length === 0) return clamped ? { ...layout, lg: placed } : layout;

  // 이미 놓인 것들의 맨 아랫줄부터 이어 붙인다.
  let y = placed.reduce((max, g) => Math.max(max, g.y + g.h), 0);
  let x = 0;
  let rowHeight = 0;
  const added: GridItem[] = missing.map((w) => {
    const size = DEFAULT_SIZE[w.template] ?? DEFAULT_SIZE.STAT_CARD;
    if (x + size.w > cols) {
      x = 0;
      y += rowHeight;
      rowHeight = 0;
    }
    const item: GridItem = {
      i: w.id,
      x,
      y,
      w: size.w,
      h: size.h,
      minW: size.minW,
      minH: size.minH,
    };
    x += size.w;
    rowHeight = Math.max(rowHeight, size.h);
    return item;
  });
  return { ...layout, lg: [...placed, ...added] };
};
