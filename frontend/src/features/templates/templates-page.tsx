import { useMemo, useState, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { DEFAULT_SIZE } from '@/features/dashboard/layout-mapper';
import { resolveWidgetRenderer } from '@/features/widgets/renderer-registry';
import { formatCell } from '@/features/widgets/widget-data';
import { api } from '@/lib/http';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import type { WidgetSpec, WidgetTemplateListResponse, WidgetTemplateResponse } from '@/types/api';

/** 카탈로그의 family 순서. 서버는 이 순서로 내려주고 화면은 그대로 묶는다. */
const FAMILY_ORDER = ['수치', '추이', '분포', '구성', '변화', '점검'];

const FAMILY_HINT: Record<string, string> = {
  수치: '지금 위치',
  추이: '시간이 지나며',
  분포: '어디에 몰렸나',
  구성: '무엇으로 이뤄졌나',
  변화: '순위와 기울기',
  점검: '하나씩 짚기',
};

const MEASURE_TYPE_LABEL: Record<string, string> = {
  COUNT: '건수',
  RATE_PCT: '비율(%)',
  DAYS: '일수',
  PCT_POINT: '편차(%p)',
};

const TIME_AXIS_LABEL: Record<WidgetTemplateResponse['timeAxis'], string> = {
  REQUIRED: '기간 차원이 있어야 한다',
  OPTIONAL: '기간 차원이 있으면 추이, 없으면 범주',
  NONE: '기간 차원을 쓰지 않는다',
};

const OPTION_LABEL: Record<string, string> = {
  unit: '단위 표기',
  sort: '정렬',
  threshold: '임계값(경고·위험)',
  stacked: '누적',
  showLegend: '범례 표시',
  compareWithPrevious: '직전 구간 비교',
  columns: '보일 열 선택',
};

const ROW = 'grid grid-cols-[9rem_1fr] gap-x-4 gap-y-1 py-1.5 text-sm';
const KEY = 'text-muted-foreground';
const SAMPLE_ROWS = 12;

/**
 * 인포 템플릿 쇼케이스 (ARC-012). 플랫폼 관리자용.
 *
 * 템플릿은 화면 조각이 아니라 입력 계약이다. "이런 모양의 값이 들어오면 이렇게 그려진다"를
 * 예시 값과 그려진 결과로 나란히 보여 준다. 예시 값은 서버가 계약에서 만들어 내려준다.
 * 프런트에 표본 파일을 두지 않는다.
 */
export function TemplatesPage(): ReactNode {
  const state = useAsync<WidgetTemplateListResponse>(
    () => api.get<WidgetTemplateListResponse>('/widget-templates'),
    [],
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  return (
    <>
      <PageHeader
        guide="admin#templates"
        title="인포 템플릿"
      />
      <DataState state={state} onRetry={state.reload}>
        {(list) => {
          const selected =
            list.templates.find((t) => t.key === selectedKey) ?? list.templates[0] ?? null;
          return (
            <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
              <TemplateList
                templates={list.templates}
                selectedKey={selected?.key ?? null}
                onSelect={setSelectedKey}
              />
              {selected && <TemplateDetail key={selected.key} template={selected} />}
            </div>
          );
        }}
      </DataState>
    </>
  );
}

function TemplateList({
  templates,
  selectedKey,
  onSelect,
}: {
  templates: WidgetTemplateResponse[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}): ReactNode {
  const groups = useMemo(
    () =>
      FAMILY_ORDER.map((family) => ({
        family,
        items: templates.filter((t) => t.family === family),
      })).filter((g) => g.items.length > 0),
    [templates],
  );
  return (
    <nav className="flex flex-col gap-4" aria-label="템플릿 목록">
      {groups.map((group) => (
        <div key={group.family}>
          <p className="text-muted-foreground mb-1 px-2 text-xs font-medium">
            {group.family} · {FAMILY_HINT[group.family] ?? ''}
          </p>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((t) => (
              <li key={t.key}>
                <button
                  type="button"
                  onClick={() => onSelect(t.key)}
                  aria-current={selectedKey === t.key ? 'true' : undefined}
                  className={cn(
                    'flex w-full flex-col items-start rounded-md px-2 py-1.5 text-left transition-colors',
                    selectedKey === t.key
                      ? 'bg-accent text-accent-foreground'
                      : 'hover:bg-accent/60',
                  )}
                >
                  <span className="text-sm font-medium">{t.label}</span>
                  <span className="text-muted-foreground font-mono text-[11px]">{t.key}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function TemplateDetail({ template: t }: { template: WidgetTemplateResponse }): ReactNode {
  const size = DEFAULT_SIZE[t.key];
  const dims = t.dimsMin === t.dimsMax ? `${t.dimsMin}개` : `${t.dimsMin}~${t.dimsMax}개`;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <ShowcaseCard template={t} />
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            <span>{t.label}</span>
            <Badge variant="outline" className="font-mono">
              {t.key}
            </Badge>
            <Badge variant="secondary">{t.family}</Badge>
            {t.chat && <Badge variant="secondary">AI 답변에 사용</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <p className="font-medium">{t.purpose}</p>
          <p className="text-muted-foreground">{t.screen}</p>
          {t.note && <p className="rounded bg-muted p-2 text-xs">{t.note}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">언제 고르나 · 모델의 판단 근거</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p className="font-medium">{t.when}</p>
          <p className="text-muted-foreground text-xs">
            위젯 생성과 AI 질의 라우팅 프롬프트에 이 문장이 그대로 들어갑니다. 모델은 그림 이름이
            아니라 이 문장과 아래 입력 계약을 보고 템플릿을 고릅니다. 문장을 고치면 모델의 기준도
            같이 바뀝니다.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">입력 계약</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col">
          <div className={ROW}>
            <span className={KEY}>받는 지표</span>
            <span>
              {t.measureTypes.length === 4
                ? '모든 유형'
                : t.measureTypes.map((m) => MEASURE_TYPE_LABEL[m] ?? m).join(' · ')}
            </span>
          </div>
          <Separator />
          <div className={ROW}>
            <span className={KEY}>차원 수</span>
            <span>{dims}</span>
          </div>
          <Separator />
          <div className={ROW}>
            <span className={KEY}>시간축</span>
            <span>{TIME_AXIS_LABEL[t.timeAxis]}</span>
          </div>
          <Separator />
          <div className={ROW}>
            <span className={KEY}>읽을 수 있는 범주</span>
            <span>
              {t.categoryMax === null
                ? `제한 없음 (행 ${t.rowCap}개까지)`
                : `${t.categoryMax}개 이하`}
            </span>
          </div>
          <Separator />
          <div className={ROW}>
            <span className={KEY}>함께 쓰는 값</span>
            <span>
              {[
                t.usesTotal && '전체 값',
                t.usesTarget && '목표값',
                t.usesPrevious && '직전 구간 값',
              ]
                .filter(Boolean)
                .join(' · ') || '없음'}
            </span>
          </div>
          <Separator />
          <div className={ROW}>
            <span className={KEY}>옵션</span>
            <span>
              {t.options.length ? t.options.map((o) => OPTION_LABEL[o] ?? o).join(' · ') : '없음'}
            </span>
          </div>
          <Separator />
          <div className={ROW}>
            <span className={KEY}>기본 크기</span>
            <span>
              {size.w}×{size.h}칸 (최소 {size.minW}×{size.minH})
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/** 예시 값과 그 값으로 그려진 결과를 나란히. 값은 서버가 계약에서 만든 것이다. */
function ShowcaseCard({ template: t }: { template: WidgetTemplateResponse }): ReactNode {
  const data = t.sample;
  const spec: WidgetSpec = {
    template: t.key,
    title: t.example.title,
    query: {
      measure: t.example.measure,
      dimensions: t.example.dimensions,
      filters: [],
      projectScope: [],
      limit: null,
    },
    options: null,
  };
  const Renderer = resolveWidgetRenderer(t.key);
  const size = DEFAULT_SIZE[t.key];
  const shown = data.rows.slice(0, SAMPLE_ROWS);
  const extras = [
    data.total && `전체 값 ${formatCell(data.total.values.value)}${data.unit ?? ''}`,
    data.previousTotal &&
      `직전 구간 ${formatCell(data.previousTotal.values.value)}${data.unit ?? ''}`,
    data.target !== null && `목표값 ${data.target}${data.unit ?? ''}`,
  ].filter(Boolean);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">
          예시 · {t.example.title}
          <span className="text-muted-foreground ml-2 font-mono text-xs">
            {t.example.measure}
            {t.example.dimensions.length ? ` × ${t.example.dimensions.join(', ')}` : ''}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex min-w-0 flex-col gap-2">
          <p className="text-muted-foreground text-xs font-medium">
            들어오는 값 · 행 {data.rows.length}개
            {data.rows.length > SAMPLE_ROWS ? ` 중 ${SAMPLE_ROWS}개` : ''}
          </p>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs">
              <thead className="bg-muted/50">
                <tr>
                  {data.columns.map((c) => (
                    <th key={c.key} className="px-2 py-1.5 text-left font-medium">
                      {c.label}
                      <span className="text-muted-foreground ml-1 font-mono font-normal">
                        {c.key}·{c.type}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((row, i) => (
                  <tr key={i} className="border-t">
                    {data.columns.map((c) => (
                      <td key={c.key} className="px-2 py-1 tabular-nums">
                        {formatCell(row.values[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {extras.length > 0 && (
            <p className="text-muted-foreground text-xs">{extras.join(' · ')}</p>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <p className="text-muted-foreground text-xs font-medium">그려지는 결과</p>
          <div
            style={{ height: Math.min(size.h * 80 + (size.h - 1) * 16, 420) }}
            className="rounded-md border p-3"
          >
            <Renderer spec={spec} data={data} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
