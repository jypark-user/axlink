import type { WidgetColumn, WidgetDataResponse, WidgetOptions, WidgetRow } from '@/types/api';

export interface Series {
  key: string;
  label: string;
  color: string;
}

const NUMERIC_TYPES = new Set(['number', 'percent', 'COUNT', 'RATE_PCT', 'DAYS', 'PCT_POINT']);

export const isNumericColumn = (column: WidgetColumn): boolean => NUMERIC_TYPES.has(column.type);

/**
 * 알 수 없는 값을 축 이름·키로 쓸 문자열로 만든다.
 * 그냥 String() 을 쓰면 객체가 '[object Object]' 로 새어 나가 축이 통째로 뭉개진다.
 */
export const asText = (value: unknown): string => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  // 객체·심볼·함수. JSON.stringify 는 심볼·함수에 undefined 를 준다.
  return JSON.stringify(value) ?? '';
};

/**
 * 이름 열(`d0_label`)이 같이 온 차원의 식별자 열(`d0`). 사람이 읽을 이름이 있으면
 * uuid 는 안 보여도 된다. 표에 보이는 열을 고를 때 기본으로 숨긴다.
 */
export const isIdColumn = (column: WidgetColumn, data: WidgetDataResponse): boolean =>
  data.columns.some((other) => other.key === `${column.key}_label`);

/** 열 설정이 없을 때 표에 보이는 열. 식별자 열은 이름 열이 있으면 숨긴다 */
export const defaultColumns = (data: WidgetDataResponse): WidgetColumn[] =>
  data.columns.filter((c) => !isIdColumn(c, data));

export const resolveColumns = (
  data: WidgetDataResponse,
  options: WidgetOptions | null,
): WidgetColumn[] => {
  const wanted = options?.columns;
  if (!wanted || wanted.length === 0) return defaultColumns(data);
  return wanted
    .map((key) => data.columns.find((c) => c.key === key))
    .filter((c): c is WidgetColumn => c !== undefined);
};

export const toSeries = (data: WidgetDataResponse): Series[] =>
  data.columns
    .filter(isNumericColumn)
    .map((c, i) => ({ key: c.key, label: c.label, color: `var(--chart-${(i % 8) + 1})` }));

/**
 * 범주 축으로 쓸 컬럼 키. 행의 실제 키는 `d0`·`value` 이고 `data.dimensions` 는
 * 카탈로그 식별자(`issue_severity`)라 서로 다르다. 행에 없는 키를 축으로 주면
 * 차트가 조용히 인덱스(0,1,2…)를 대신 그린다.
 */
export const categoryKey = (data: WidgetDataResponse): string | null => {
  const text = data.columns.filter((c) => !isNumericColumn(c));
  // 값이 UUID 인 차원(프로젝트 등)은 `<키>_label` 에 사람이 읽는 이름이 함께 온다.
  return (
    text.find((c) => c.key.endsWith('_label'))?.key ?? text[0]?.key ?? data.columns[0]?.key ?? null
  );
};

export const rowValues = (rows: WidgetRow[]): Record<string, unknown>[] =>
  rows.map((r) => r.values ?? {});

export const numberAt = (row: WidgetRow | null, key: string): number | null => {
  const raw = row?.values?.[key];
  if (typeof raw === 'number') return raw;
  if (typeof raw === 'string' && raw.trim() !== '' && !Number.isNaN(Number(raw)))
    return Number(raw);
  return null;
};

export const pickTotal = (
  data: WidgetDataResponse,
): { value: number | null; column: WidgetColumn | null } => {
  const column = data.columns.find(isNumericColumn) ?? null;
  if (!column) return { value: null, column: null };
  const fromTotal = numberAt(data.total, column.key);
  if (fromTotal !== null) return { value: fromTotal, column };
  return { value: numberAt(data.rows[0] ?? null, column.key), column };
};

export const pickDelta = (
  data: WidgetDataResponse,
): { diff: number; ratio: number; direction: 'up' | 'down' | 'flat' } | null => {
  const column = data.columns.find(isNumericColumn);
  if (!column || data.previousTotal === null) return null;
  const prev = numberAt(data.previousTotal, column.key);
  const cur = pickTotal(data).value;
  if (prev === null || cur === null) return null;
  const diff = cur - prev;
  const ratio = prev === 0 ? 0 : diff / prev;
  const direction = diff > 0 ? 'up' : diff < 0 ? 'down' : 'flat';
  return { diff, ratio, direction };
};

export const formatCell = (value: unknown): string => {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') return value.toLocaleString('ko-KR');
  if (typeof value === 'boolean') return value ? '예' : '아니오';
  return asText(value);
};

export interface Pivoted {
  xKey: string;
  rows: Record<string, unknown>[];
  series: Series[];
}

/**
 * 두 차원 결과를 넓은 표로 편다. 서버는 `{d0, d1, value}` 한 줄씩 길게 주는데,
 * 누적 막대는 `{d0, A: 3, B: 5}` 모양을 원한다. 두 축이 아니면 null.
 */
export const pivot = (data: WidgetDataResponse): Pivoted | null => {
  const text = data.columns.filter((c) => !isNumericColumn(c));
  const pick = (n: number) =>
    text.find((c) => c.key === `d${n}_label`) ?? text.find((c) => c.key === `d${n}`);
  const xCol = pick(0);
  const seriesCol = pick(1);
  const valueCol = data.columns.find(isNumericColumn);
  if (!xCol || !seriesCol || !valueCol) return null;

  const byX = new Map<string, Record<string, unknown>>();
  const names: string[] = [];
  for (const row of rowValues(data.rows)) {
    const x = asText(row[xCol.key]);
    const name = asText(row[seriesCol.key]);
    if (!names.includes(name)) names.push(name);
    const bucket = byX.get(x) ?? { [xCol.key]: x };
    bucket[name] = Number(row[valueCol.key] ?? 0);
    byX.set(x, bucket);
  }
  return {
    xKey: xCol.key,
    rows: [...byX.values()],
    series: names.map((name, i) => ({
      key: name,
      label: name,
      color: `var(--chart-${(i % 8) + 1})`,
    })),
  };
};
