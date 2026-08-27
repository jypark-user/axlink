import { type ReactElement } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Label,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceLine,
  Treemap,
  XAxis,
  YAxis,
} from 'recharts';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { badgeVariantFor, label as labelOf } from '@/lib/labels';
import {
  formatCell,
  numberAt,
  pickDelta,
  pickTotal,
  resolveColumns,
  rowValues,
  toSeries,
  pivot,
  categoryKey,
  asText,
  type Series,
} from '@/features/widgets/widget-data';
import type { WidgetRendererProps } from '@/features/widgets/widget-types';
import type { WidgetRow } from '@/types/api';

const axisKey = (props: WidgetRendererProps): string => categoryKey(props.data) ?? 'name';

/**
 * 계열을 shadcn 차트 설정으로 옮긴다 — 툴팁·범례가 이름을 여기서 읽는다.
 * 색은 넣지 않는다: 계열 키가 데이터에서 오는 값(용역사 이름 등)이라 CSS 변수 이름으로 쓰면 깨진다.
 * 색은 지금처럼 fill·stroke 로 직접 준다.
 */
const chartConfig = (series: Series[]): ChartConfig =>
  Object.fromEntries(series.map((s) => [s.key, { label: labelOf(s.label) }]));

/** 축·격자 기본값 — shadcn 차트는 선을 지우고 눈금 글씨만 남긴다. */
const AXIS = { tickLine: false, axisLine: false, tickMargin: 8, tick: { fontSize: 11 } } as const;

const Tip = <ChartTooltip cursor={false} content={<ChartTooltipContent />} />;

const legendShown = (props: WidgetRendererProps): boolean =>
  props.spec.options?.showLegend !== false;

function NoData(): ReactElement {
  return (
    <p className="py-6 text-center text-sm text-muted-foreground">표시할 데이터가 없습니다.</p>
  );
}

/**
 * 카드 안에 눕는 작은 추세선. 축도 눈금도 없이 방향만 보여준다 —
 * 숫자 하나로는 오르는 중인지 내리는 중인지 알 수 없다. (ax-pms KpiGridSection 과 같은 구성)
 */
function Sparkline({ values }: { values: number[] }): ReactElement | null {
  if (values.length < 2) return null;
  const w = 96;
  const h = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const x = (i: number) => 2 + (i * (w - 4)) / (values.length - 1);
  const y = (v: number) => 3 + (1 - (v - min) / range) * (h - 6);
  const path = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ');

  return (
    <svg width={w} height={h} aria-hidden className="shrink-0 overflow-visible">
      <path
        d={path}
        fill="none"
        stroke="var(--color-primary)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={x(values.length - 1)}
        cy={y(values[values.length - 1])}
        r="2.5"
        fill="var(--color-primary)"
        stroke="var(--color-background)"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function StatCardWidget({ spec, data }: WidgetRendererProps): ReactElement {
  const { value, column } = pickTotal(data);
  const delta = spec.options?.compareWithPrevious === false ? null : pickDelta(data);
  const unit = spec.options?.unit ?? data.unit ?? '';
  // 기간 축이 붙어 있으면 행이 곧 시계열이다 — 그럴 때만 추세선을 그린다.
  const series =
    data.rows.length >= 2 && column ? data.rows.map((r) => numberAt(r, column.key) ?? 0) : [];
  const threshold = spec.options?.threshold ?? null;
  const tone =
    threshold && value !== null
      ? value >= threshold.critical
        ? 'text-destructive'
        : value >= threshold.warn
          ? 'text-warning'
          : ''
      : '';
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-end justify-between gap-2">
        <p className={`text-3xl font-semibold tabular-nums ${tone}`}>
          {value === null ? '-' : value.toLocaleString('ko-KR')}
          {unit && <span className="ml-1 text-base font-normal text-muted-foreground">{unit}</span>}
        </p>
        <Sparkline values={series} />
      </div>
      <p className="text-xs text-muted-foreground">{column?.label ?? data.measureLabel}</p>
      {delta && (
        <Badge
          variant={
            delta.direction === 'up' ? 'info' : delta.direction === 'down' ? 'secondary' : 'outline'
          }
        >
          {delta.direction === 'up' ? '▲' : delta.direction === 'down' ? '▼' : '='}{' '}
          {Math.abs(delta.diff).toLocaleString('ko-KR')} ({(delta.ratio * 100).toFixed(1)}%)
        </Badge>
      )}
    </div>
  );
}

export function BarChartWidget(props: WidgetRendererProps): ReactElement {
  const { data, spec } = props;
  const series = toSeries(data);
  if (data.rows.length === 0 || series.length === 0) return <NoData />;
  const stacked = spec.options?.stacked === true;
  return (
    <ChartContainer config={chartConfig(series)} className="h-full w-full">
      <BarChart data={rowValues(data.rows)}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={axisKey(props)} {...AXIS} />
        <YAxis {...AXIS} width={40} />
        {Tip}
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            fill={s.color}
            stackId={stacked ? 'stack' : undefined}
            radius={[2, 2, 0, 0]}
          />
        ))}
      </BarChart>
    </ChartContainer>
  );
}

export function LineChartWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const series = toSeries(data);
  if (data.rows.length === 0 || series.length === 0) return <NoData />;
  return (
    <ChartContainer config={chartConfig(series)} className="h-full w-full">
      <LineChart data={rowValues(data.rows)}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={axisKey(props)} {...AXIS} />
        <YAxis {...AXIS} width={40} />
        {Tip}
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            dot={false}
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}

export function PieChartWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const series = toSeries(data);
  const valueKey = series[0]?.key;
  if (data.rows.length === 0 || !valueKey) return <NoData />;
  const rows = rowValues(data.rows);
  return (
    <ChartContainer config={chartConfig(series)} className="h-full w-full">
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent nameKey={axisKey(props)} hideLabel />} />
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        <Pie
          data={rows}
          dataKey={valueKey}
          nameKey={axisKey(props)}
          innerRadius="45%"
          outerRadius="75%"
        >
          {rows.map((_, i) => (
            <Cell key={i} fill={`var(--chart-${(i % 8) + 1})`} />
          ))}
        </Pie>
      </PieChart>
    </ChartContainer>
  );
}

export function ProgressListWidget({ spec, data }: WidgetRendererProps): ReactElement {
  const series = toSeries(data);
  const valueKey = series[0]?.key;
  const nameKey = categoryKey(data);
  if (data.rows.length === 0 || !valueKey || !nameKey) return <NoData />;
  const values = data.rows.map((r) => numberAt(r, valueKey) ?? 0);
  const max = Math.max(...values, 1);
  const unit = spec.options?.unit ?? data.unit ?? '';

  /**
   * 전체 값을 기준선으로 긋는다 — 막대만 있으면 "이게 높은 건가" 를 알 수 없다.
   * 선 왼쪽에 멈춘 항목이 전체보다 뒤처진 것이다. (ax-pms 진행 단계의 계획선과 같은 읽기)
   */
  const baseline = numberAt(data.total ?? { values: {} }, valueKey);
  const baselineAt = baseline === null ? null : Math.round((baseline / max) * 100);

  return (
    <ul className="flex flex-col gap-2">
      {data.rows.map((row, i) => {
        const pct = Math.round((values[i] / max) * 100);
        const behind = baselineAt !== null && pct < baselineAt;
        return (
          <li key={i} className="flex flex-col gap-1">
            <div className="flex justify-between text-xs">
              <span className="truncate">{formatCell(row.values?.[nameKey])}</span>
              <span
                className={`tabular-nums ${behind ? 'text-destructive' : 'text-muted-foreground'}`}
              >
                {values[i].toLocaleString('ko-KR')}
                {unit}
              </span>
            </div>
            <span className="bg-accent relative block h-2 overflow-hidden rounded-full">
              <span
                className={`block h-full rounded-full ${behind ? 'bg-destructive' : 'bg-primary'}`}
                style={{ width: `${pct}%` }}
              />
              {baselineAt !== null && (
                <span
                  aria-hidden
                  className="bg-foreground/40 absolute top-0 h-full w-px"
                  style={{ left: `${baselineAt}%` }}
                />
              )}
            </span>
          </li>
        );
      })}
      {baseline !== null && (
        <li className="text-muted-foreground text-[11px]">
          세로선 = 전체 {baseline.toLocaleString('ko-KR')}
          {unit}
        </li>
      )}
    </ul>
  );
}

export function DataTableWidget({ spec, data }: WidgetRendererProps): ReactElement {
  const columns = resolveColumns(data, spec.options);
  if (data.rows.length === 0 || columns.length === 0) return <NoData />;

  // 열은 위젯 명세가 정하므로 여기서 만든다.
  const tableColumns: ColumnDef<WidgetRow, unknown>[] = columns.map((c) => ({
    id: c.key,
    accessorFn: (row) => row.values?.[c.key],
    header: ({ column }) => <SortableHeader column={column}>{c.label}</SortableHeader>,
    cell: ({ row }) => formatCell(row.original.values?.[c.key]),
  }));

  return (
    <DataTable<WidgetRow, unknown>
      columns={tableColumns}
      data={data.rows}
      paginated={data.rows.length > 20}
      pageSize={20}
    />
  );
}

/**
 * 상태 흐름 띠 — 정의→설계→구현→검증→인수처럼 단계가 있는 것을 100% 한 줄로 눕힌다.
 * 막대 차트로 그리면 단계별 높이 비교가 되지만, 전체 중 어디에 고여 있는지는 안 보인다.
 */
export function StatusFlowWidget({ spec, data }: WidgetRendererProps): ReactElement {
  const series = toSeries(data);
  const valueKey = series[0]?.key;
  const nameKey = categoryKey(data);
  if (data.rows.length === 0 || !valueKey || !nameKey) return <NoData />;

  const parts = data.rows.map((row) => ({
    name: String(formatCell(row.values?.[nameKey])),
    value: numberAt(row, valueKey) ?? 0,
  }));
  const sum = parts.reduce((acc, p) => acc + p.value, 0);
  if (sum <= 0) return <NoData />;
  const unit = spec.options?.unit ?? data.unit ?? '';

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-accent flex h-6 w-full overflow-hidden rounded-full">
        {parts.map((part, i) => (
          <span
            key={part.name}
            title={`${part.name} ${part.value.toLocaleString('ko-KR')}${unit}`}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{
              width: `${(part.value / sum) * 100}%`,
              backgroundColor: `var(--chart-${(i % 8) + 1})`,
            }}
          />
        ))}
      </div>

      <ul className="flex flex-col gap-1.5">
        {parts.map((part, i) => (
          <li key={part.name} className="flex items-center gap-2 text-xs">
            <span
              aria-hidden
              className="size-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: `var(--chart-${(i % 8) + 1})` }}
            />
            <span className="min-w-0 flex-1 truncate">{labelOf(part.name)}</span>
            <span className="tabular-nums">
              {part.value.toLocaleString('ko-KR')}
              {unit}
            </span>
            <span className="text-muted-foreground w-10 text-right tabular-nums">
              {Math.round((part.value / sum) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * 두 차원 격자 — 행 × 열이 만나는 칸의 값을 농도로 칠한다.
 * 어느 활동에서 어떤 상태로 몰려 있는지, 숫자를 읽기 전에 무늬로 먼저 보인다.
 */
export function HeatmapWidget({ spec, data }: WidgetRendererProps): ReactElement {
  const series = toSeries(data);
  const valueKey = series[0]?.key;
  const [rowKey, colKey] = data.dimensions;
  if (data.rows.length === 0 || !valueKey || !rowKey || !colKey) return <NoData />;

  const rowNames = [...new Set(data.rows.map((r) => String(formatCell(r.values?.[rowKey]))))];
  const colNames = [...new Set(data.rows.map((r) => String(formatCell(r.values?.[colKey]))))];

  const cell = new Map<string, number>();
  for (const row of data.rows) {
    const key = `${formatCell(row.values?.[rowKey])} ${formatCell(row.values?.[colKey])}`;
    cell.set(key, (cell.get(key) ?? 0) + (numberAt(row, valueKey) ?? 0));
  }
  const max = Math.max(...cell.values(), 1);
  const unit = spec.options?.unit ?? data.unit ?? '';

  return (
    <div className="overflow-auto">
      <table className="w-full border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th className="text-muted-foreground w-24 text-left font-normal" />
            {colNames.map((col) => (
              <th key={col} className="text-muted-foreground px-1 font-normal whitespace-nowrap">
                {labelOf(col)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowNames.map((row) => (
            <tr key={row}>
              <th className="text-muted-foreground max-w-24 truncate pr-2 text-left font-normal">
                {labelOf(row)}
              </th>
              {colNames.map((col) => {
                const value = cell.get(`${row} ${col}`) ?? 0;
                return (
                  <td
                    key={col}
                    title={`${labelOf(row)} · ${labelOf(col)} — ${value.toLocaleString('ko-KR')}${unit}`}
                    className="rounded-sm text-center tabular-nums"
                    style={{
                      // 0 은 칠하지 않는다 — 빈 칸이 곧 '없음' 이다.
                      backgroundColor:
                        value === 0
                          ? 'var(--color-muted)'
                          : `color-mix(in oklab, var(--color-primary) ${15 + (value / max) * 70}%, transparent)`,
                    }}
                  >
                    {value === 0 ? '' : value.toLocaleString('ko-KR')}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChecklistWidget({ spec, data }: WidgetRendererProps): ReactElement {
  const columns = resolveColumns(data, spec.options);
  const statusColumn = columns.find(
    (c) => c.type === 'status' || c.key.toLowerCase().includes('status'),
  );
  const nameKey = categoryKey(data) ?? columns[0]?.key;
  if (data.rows.length === 0 || !nameKey) return <NoData />;
  return (
    <ul className="flex flex-col divide-y">
      {data.rows.map((row, i) => {
        const status = statusColumn ? asText(row.values?.[statusColumn.key]) : '';
        return (
          <li key={i} className="flex items-center justify-between gap-2 py-1.5 text-sm">
            <span className="truncate">{formatCell(row.values?.[nameKey])}</span>
            {status && <Badge variant={badgeVariantFor(status)}>{labelOf(status)}</Badge>}
          </li>
        );
      })}
    </ul>
  );
}

export function GanttSummaryWidget({ data }: WidgetRendererProps): ReactElement {
  const nameKey = categoryKey(data);
  const plannedKey = data.columns.find((c) => c.key.toLowerCase().includes('planned'))?.key;
  const actualKey = data.columns.find((c) => c.key.toLowerCase().includes('actual'))?.key;
  if (data.rows.length === 0 || !nameKey || !plannedKey || !actualKey) return <NoData />;
  return (
    <ul className="flex flex-col gap-2">
      {data.rows.map((row, i) => {
        const planned = numberAt(row, plannedKey) ?? 0;
        const actual = numberAt(row, actualKey) ?? 0;
        return (
          <li key={i} className="flex flex-col gap-1">
            <div className="flex justify-between text-xs">
              <span className="truncate">{formatCell(row.values?.[nameKey])}</span>
              <span className="tabular-nums text-muted-foreground">
                계획 {planned}% · 실적 {actual}%
              </span>
            </div>
            <div className="relative h-3 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className="absolute inset-y-0 left-0 bg-muted-foreground/40"
                style={{ width: `${Math.min(planned, 100)}%` }}
              />
              <div
                className={`absolute inset-y-0 left-0 ${actual < planned ? 'bg-warning' : 'bg-primary'}`}
                style={{ width: `${Math.min(actual, 100)}%`, height: '50%', top: '25%' }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function UnsupportedWidget({ spec }: WidgetRendererProps): ReactElement {
  return (
    <Alert variant="destructive">
      <AlertTitle>지원하지 않는 위젯 유형입니다: {String(spec.template)}</AlertTitle>
      <AlertDescription>이 위젯을 삭제하거나 지원되는 템플릿으로 다시 만드세요.</AlertDescription>
    </Alert>
  );
}

/** 면적 추이 — 구간이 길어 선이 빽빽할 때 흐름을 본다. */
export function AreaChartWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const series = toSeries(data);
  if (data.rows.length === 0 || series.length === 0) return <NoData />;
  return (
    <ChartContainer config={chartConfig(series)} className="h-full w-full">
      <AreaChart data={rowValues(data.rows)}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={axisKey(props)} {...AXIS} />
        <YAxis {...AXIS} width={40} />
        {Tip}
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            fill={s.color}
            fillOpacity={0.18}
            stackId="stack"
          />
        ))}
      </AreaChart>
    </ChartContainer>
  );
}

/** 가로 막대 — 항목이 많거나 이름이 길 때 순위를 본다. */
export function HorizontalBarChartWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const series = toSeries(data);
  if (data.rows.length === 0 || series.length === 0) return <NoData />;
  const key = axisKey(props);
  // 큰 값이 위로 오게 세운다 — 순위를 보려고 쓰는 그림이다.
  const rows = [...rowValues(data.rows)].sort(
    (a, b) => Number(b[series[0].key] ?? 0) - Number(a[series[0].key] ?? 0),
  );
  return (
    <ChartContainer
      config={chartConfig(series)}
      className="h-full w-full"
      style={{ minHeight: Math.max(160, rows.length * 24) }}
    >
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" {...AXIS} />
        <YAxis type="category" dataKey={key} {...AXIS} width={110} />
        {Tip}
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={[0, 2, 2, 0]} />
        ))}
      </BarChart>
    </ChartContainer>
  );
}

/** 누적 막대 — 범주 안에서 무엇이 얼마씩 차지하는지 본다. 두 축 결과를 펴서 쓴다. */
export function StackedBarChartWidget(props: WidgetRendererProps): ReactElement {
  const wide = pivot(props.data);
  if (!wide || wide.rows.length === 0) return <BarChartWidget {...props} />;
  return (
    <ChartContainer config={chartConfig(wide.series)} className="h-full w-full">
      <BarChart data={wide.rows}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={wide.xKey} {...AXIS} />
        <YAxis {...AXIS} width={40} />
        {Tip}
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        {wide.series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} stackId="stack" />
        ))}
      </BarChart>
    </ChartContainer>
  );
}

/** 도넛 — 구성비를 보되 가운데에 총계를 둔다. */
export function DonutChartWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const series = toSeries(data);
  if (data.rows.length === 0 || series.length === 0) return <NoData />;
  const key = series[0].key;
  const rows = rowValues(data.rows);
  const sum = rows.reduce((acc, r) => acc + Number(r[key] ?? 0), 0);
  return (
    <ChartContainer config={chartConfig(series)} className="h-full w-full">
      <PieChart>
        <Pie data={rows} dataKey={key} nameKey={axisKey(props)} innerRadius="55%" outerRadius="80%">
          {rows.map((_, i) => (
            <Cell key={i} fill={`var(--chart-${(i % 8) + 1})`} />
          ))}
          {/* 총계는 카드가 아니라 도넛 한가운데에 놓는다 — 범례가 붙으면 원이 위로 밀리므로
              카드 기준으로 겹쳐 놓으면 어긋난다. viewBox 의 cx·cy 가 원의 실제 중심이다. */}
          <Label
            position="center"
            content={({ viewBox }) => {
              const box = viewBox as { cx?: number; cy?: number } | undefined;
              if (!box?.cx || !box?.cy) return null;
              return (
                <g>
                  <text
                    x={box.cx}
                    y={box.cy}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className="fill-foreground text-base font-semibold tabular-nums"
                  >
                    {sum.toLocaleString('ko-KR')}
                  </text>
                  <text
                    x={box.cx}
                    y={box.cy + 16}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className="fill-muted-foreground text-[10px]"
                  >
                    {data.unit ?? '합계'}
                  </text>
                </g>
              );
            }}
          />
        </Pie>
        <ChartTooltip content={<ChartTooltipContent nameKey={axisKey(props)} hideLabel />} />
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
      </PieChart>
    </ChartContainer>
  );
}

/** 방사형 — 항목별 이행률이 고른지 한눈에 본다. */
export function RadarChartWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const series = toSeries(data);
  if (data.rows.length < 3 || series.length === 0) return <BarChartWidget {...props} />;
  return (
    <ChartContainer config={chartConfig(series)} className="h-full w-full">
      <RadarChart data={rowValues(data.rows)} outerRadius="70%">
        <PolarGrid />
        <PolarAngleAxis dataKey={axisKey(props)} tick={{ fontSize: 11 }} />
        <PolarRadiusAxis tick={{ fontSize: 10 }} />
        {Tip}
        {series.map((s) => (
          <Radar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            fill={s.color}
            fillOpacity={0.25}
          />
        ))}
      </RadarChart>
    </ChartContainer>
  );
}

/**
 * 누적 흐름 — 기간 위에 상태별 건수를 쌓아 올린다.
 * 쌓이는 속도가 닫히는 속도를 앞지르면 위쪽 띠가 계속 두꺼워진다. 그 벌어짐이 적체다.
 */
export function CumulativeFlowWidget(props: WidgetRendererProps): ReactElement {
  const wide = pivot(props.data);
  if (!wide || wide.rows.length < 2) return <AreaChartWidget {...props} />;

  // 기간마다의 값을 앞에서부터 더해 나간다 — 흐름은 그 시점까지의 총량으로 봐야 한다.
  const running: Record<string, number> = {};
  const rows = wide.rows.map((row) => {
    const next: Record<string, unknown> = { [wide.xKey]: row[wide.xKey] };
    for (const s of wide.series) {
      running[s.key] = (running[s.key] ?? 0) + Number(row[s.key] ?? 0);
      next[s.key] = running[s.key];
    }
    return next;
  });

  return (
    <ChartContainer config={chartConfig(wide.series)} className="h-full w-full">
      <AreaChart data={rows}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={wide.xKey} {...AXIS} />
        <YAxis {...AXIS} width={40} />
        {Tip}
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        {wide.series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stackId="flow"
            stroke={s.color}
            fill={s.color}
            fillOpacity={0.35}
          />
        ))}
      </AreaChart>
    </ChartContainer>
  );
}

/**
 * 파레토 — 큰 것부터 세운 막대 위에 누적 비율선을 얹는다.
 * "어디에 몰렸나" 는 막대 길이가 아니라 선이 80% 를 넘는 지점이 답한다.
 */
export function ParetoWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const key = axisKey(props);
  const valueKey = toSeries(data)[0]?.key;
  if (!valueKey || data.rows.length < 2) return <BarChartWidget {...props} />;

  const sorted = rowValues(data.rows)
    .map((r) => ({ name: asText(r[key]), value: Number(r[valueKey] ?? 0) }))
    .sort((a, b) => b.value - a.value);
  const total = sorted.reduce((sum, r) => sum + r.value, 0) || 1;
  let running = 0;
  const rows = sorted.map((r) => {
    running += r.value;
    return { ...r, cum: Math.round((running / total) * 1000) / 10 };
  });

  return (
    <ChartContainer
      config={{ value: { label: data.measureLabel }, cum: { label: '누적 비율' } }}
      className="h-full w-full"
    >
      <ComposedChart data={rows}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="name" {...AXIS} interval={0} angle={-15} textAnchor="end" />
        <YAxis yAxisId="left" {...AXIS} width={40} />
        <YAxis
          yAxisId="right"
          orientation="right"
          domain={[0, 100]}
          unit="%"
          {...AXIS}
          width={44}
        />
        {Tip}
        <Bar yAxisId="left" dataKey="value" name={data.measureLabel} fill="var(--chart-1)" />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="cum"
          name="누적 비율"
          stroke="var(--chart-3)"
          strokeWidth={2}
          dot={false}
        />
        <ReferenceLine yAxisId="right" y={80} stroke="var(--border)" strokeDasharray="4 4" />
      </ComposedChart>
    </ChartContainer>
  );
}

/** 트리맵 — 항목이 많아 막대로는 읽히지 않을 때, 넓이로 큰 덩어리를 본다. */
export function TreemapWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const key = axisKey(props);
  const valueKey = toSeries(data)[0]?.key;
  if (!valueKey || data.rows.length === 0) return <NoData />;

  const rows = rowValues(data.rows)
    .map((r, i) => ({
      name: labelOf(asText(r[key])),
      size: Math.max(Number(r[valueKey] ?? 0), 0),
      fill: `var(--chart-${(i % 8) + 1})`,
    }))
    .filter((r) => r.size > 0);
  if (rows.length === 0) return <NoData />;

  return (
    <ChartContainer config={{ size: { label: data.measureLabel } }} className="h-full w-full">
      <Treemap data={rows} dataKey="size" nameKey="name" stroke="var(--background)">
        <ChartTooltip content={<ChartTooltipContent nameKey="name" hideLabel />} />
      </Treemap>
    </ChartContainer>
  );
}

/** 처음과 끝, 두 시점만 잇는다 — 누가 올랐고 누가 내렸는지는 선의 기울기가 말한다. */
export function SlopeChartWidget(props: WidgetRendererProps): ReactElement {
  const wide = pivot(props.data);
  if (!wide || wide.rows.length < 2) return <LineChartWidget {...props} />;
  const ends = [wide.rows[0], wide.rows[wide.rows.length - 1]];

  return (
    <ChartContainer config={chartConfig(wide.series)} className="h-full w-full">
      <LineChart data={ends}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={wide.xKey} {...AXIS} />
        <YAxis {...AXIS} width={40} />
        {Tip}
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        {wide.series.map((s) => (
          <Line
            key={s.key}
            type="linear"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}

/** 순위 변화 — 값이 아니라 등수를 그린다. 위가 1등이라 자리바꿈이 눈에 띈다. */
export function BumpChartWidget(props: WidgetRendererProps): ReactElement {
  const wide = pivot(props.data);
  if (!wide || wide.rows.length < 2) return <LineChartWidget {...props} />;

  const ranked = wide.rows.map((row) => {
    const order = [...wide.series]
      .map((s) => ({ key: s.key, value: Number(row[s.key] ?? 0) }))
      .sort((a, b) => b.value - a.value);
    const next: Record<string, unknown> = { [wide.xKey]: row[wide.xKey] };
    order.forEach((s, i) => {
      next[s.key] = i + 1;
    });
    return next;
  });

  return (
    <ChartContainer config={chartConfig(wide.series)} className="h-full w-full">
      <LineChart data={ranked}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={wide.xKey} {...AXIS} />
        <YAxis
          reversed
          allowDecimals={false}
          domain={[1, wide.series.length]}
          {...AXIS}
          width={28}
        />
        <ChartTooltip
          cursor={false}
          content={<ChartTooltipContent formatter={(v) => `${asText(v)}위`} />}
        />
        {legendShown(props) && <ChartLegend content={<ChartLegendContent />} />}
        {wide.series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}

/** 항목마다 한 줄짜리 추세와 마지막 값. 여러 항목의 방향을 한 화면에서 훑을 때 쓴다. */
export function SparklineWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const unit = props.spec.options?.unit ?? data.unit ?? '';
  const wide = pivot(data);

  const lines = wide
    ? wide.series.map((s) => ({
        label: s.label,
        values: wide.rows.map((r) => Number(r[s.key] ?? 0)),
      }))
    : (() => {
        const valueKey = toSeries(data)[0]?.key;
        if (!valueKey) return [];
        return [
          {
            label: data.measureLabel,
            values: data.rows.map((r) => numberAt(r, valueKey) ?? 0),
          },
        ];
      })();

  if (lines.length === 0 || lines[0].values.length < 2) return <NoData />;

  return (
    <ul className="flex flex-col gap-2">
      {lines.map((line) => {
        const last = line.values[line.values.length - 1];
        const first = line.values[0];
        const diff = last - first;
        return (
          <li key={line.label} className="flex items-center gap-3">
            <span className="text-muted-foreground min-w-0 flex-1 truncate text-xs">
              {labelOf(line.label)}
            </span>
            <Sparkline values={line.values} />
            <span className="w-20 text-right text-sm tabular-nums">
              {last.toLocaleString('ko-KR')}
              {unit}
            </span>
            <span
              className={`w-14 text-right text-xs tabular-nums ${
                diff > 0
                  ? 'text-primary'
                  : diff < 0
                    ? 'text-muted-foreground'
                    : 'text-muted-foreground'
              }`}
            >
              {diff > 0 ? '▲' : diff < 0 ? '▼' : '='} {Math.abs(diff).toLocaleString('ko-KR')}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * 불릿 — 항목마다 목표선을 그어 둔 가로 막대.
 * 82% 가 좋은 수인지는 목표가 90% 라는 걸 알아야 말이 된다.
 */
export function BulletChartWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const key = axisKey(props);
  const valueKey = toSeries(data)[0]?.key;
  if (!valueKey || data.rows.length === 0) return <NoData />;

  const target = props.spec.options?.threshold?.warn ?? data.target ?? null;
  const unit = props.spec.options?.unit ?? data.unit ?? '';
  const rows = rowValues(data.rows).map((r) => ({
    name: labelOf(asText(r[key])),
    value: Number(r[valueKey] ?? 0),
  }));
  const max = Math.max(...rows.map((r) => r.value), target ?? 0, 1);

  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((row) => {
        const reached = target === null || row.value >= target;
        return (
          <li key={row.name} className="flex items-center gap-3">
            <span className="text-muted-foreground w-28 shrink-0 truncate text-xs">{row.name}</span>
            <span className="bg-muted relative h-3 min-w-0 flex-1 overflow-hidden rounded-sm">
              <span
                className="absolute inset-y-0 left-0 rounded-sm"
                style={{
                  width: `${(row.value / max) * 100}%`,
                  backgroundColor: reached ? 'var(--chart-1)' : 'var(--chart-3)',
                }}
              />
              {target !== null && (
                <span
                  aria-hidden
                  title={`목표 ${target.toLocaleString('ko-KR')}${unit}`}
                  className="bg-foreground absolute inset-y-0 w-0.5"
                  style={{ left: `${(target / max) * 100}%` }}
                />
              )}
            </span>
            <span className="w-16 text-right text-sm tabular-nums">
              {row.value.toLocaleString('ko-KR')}
              {unit}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** 달력 — 날짜를 요일×주 격자에 놓는다. 빈 날이 이어지는 구간이 그대로 보인다. */
export function CalendarHeatmapWidget(props: WidgetRendererProps): ReactElement {
  const { data } = props;
  const key = axisKey(props);
  const valueKey = toSeries(data)[0]?.key;
  if (!valueKey || data.rows.length === 0) return <NoData />;

  const days = rowValues(data.rows)
    .map((r) => ({ date: new Date(asText(r[key])), value: Number(r[valueKey] ?? 0) }))
    .filter((d) => !Number.isNaN(d.date.getTime()))
    .sort((a, b) => a.date.getTime() - b.date.getTime());
  if (days.length === 0) return <BarChartWidget {...props} />;

  const max = Math.max(...days.map((d) => d.value), 1);
  // 첫 날이 무슨 요일인지에 맞춰 앞을 비워 둬야 요일 줄이 어긋나지 않는다.
  const pad = days[0].date.getDay();
  const unit = props.spec.options?.unit ?? data.unit ?? '';

  return (
    <div className="flex flex-col gap-1">
      <div className="grid grid-flow-col grid-rows-7 gap-0.5">
        {Array.from({ length: pad }, (_, i) => (
          <span key={`pad-${i}`} className="size-3" />
        ))}
        {days.map((day) => (
          <span
            key={day.date.toISOString()}
            title={`${day.date.toLocaleDateString('ko-KR')} — ${day.value.toLocaleString('ko-KR')}${unit}`}
            className="size-3 rounded-[2px]"
            style={{
              backgroundColor:
                day.value === 0
                  ? 'var(--color-muted)'
                  : `color-mix(in oklab, var(--color-primary) ${20 + (day.value / max) * 70}%, transparent)`,
            }}
          />
        ))}
      </div>
      <p className="text-muted-foreground text-xs">
        {days[0].date.toLocaleDateString('ko-KR')} ~{' '}
        {days[days.length - 1].date.toLocaleDateString('ko-KR')}
      </p>
    </div>
  );
}
