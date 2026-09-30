import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { useAuth } from '@/features/auth/auth-context';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import type { ProgressSnapshotResponse, ProjectScheduleResponse } from '@/types/api';

/**
 * 스냅샷 화면. 하루 한 줄로 고정한 지표가 어떻게 관리되고 있는지, 값이 어떻게 움직였는지를
 * 이 화면 하나로 본다. 위는 언제 찍히고 다음은 언제인지, 가운데는 진척·계획 추이, 아래는
 * 줄마다 전날 대비 변화가 붙은 표다. 동기화(도구에서 읽어 오기)와는 다른 것이다.
 */

const CHART: ChartConfig = {
  representativePct: { label: '진척률', color: 'var(--chart-1)' },
  wbsPlannedPct: { label: '계획', color: 'var(--chart-2)' },
};

const LEVEL_LABEL: Record<string, string> = {
  L1: 'WBS 실적',
  L2: 'WBS 추정',
  L3: '이슈 기반',
  L4: '산출물 기반',
  NONE: '산정 불가',
};

export function SnapshotsPage(): ReactNode {
  const { project } = useProjectContext();
  const { me } = useAuth();
  const { toast } = useToast();
  const [taking, setTaking] = useState(false);

  const state = useAsync<ProgressSnapshotResponse[]>(
    () => api.get<ProgressSnapshotResponse[]>(`/projects/${project.id}/snapshots?limit=120`),
    [project.id],
  );
  const schedule = useAsync<ProjectScheduleResponse>(
    () => api.get<ProjectScheduleResponse>(`/projects/${project.id}/schedule`),
    [project.id],
  );
  const canTake = me?.role === 'CLIENT' || me?.role === 'SUPER_ADMIN';

  const takeNow = async () => {
    setTaking(true);
    try {
      await api.post(`/projects/${project.id}/snapshots`, {});
      toast({ title: '오늘 스냅샷을 다시 찍었습니다.', variant: 'success' });
      state.reload();
      schedule.reload();
    } catch (err) {
      toast({
        title: '찍지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setTaking(false);
    }
  };

  return (
    <>
      <PageHeader
        title="스냅샷"
        description="매일 한 번 지표를 한 줄로 고정한 기록입니다. 도구에서 읽어 오는 동기화와는 다른 것으로, 이 기록이 추이 그래프와 보고서 수치의 출처입니다."
        actions={
          canTake ? (
            <Button size="sm" onClick={() => void takeNow()} disabled={taking}>
              {taking ? '찍는 중…' : '지금 찍기'}
            </Button>
          ) : null
        }
      />

      <DataState state={schedule} onRetry={schedule.reload}>
        {(s) => (
          <p className="text-muted-foreground mb-5 text-sm tnum">
            마지막 기록 {s.lastSnapshotDate ? formatDate(s.lastSnapshotDate) : '없음'} · 다음{' '}
            {formatDateTime(s.nextSnapshotAt)} ({s.timezone}) · 빈도{' '}
            {s.snapshotOptions.find((o) => o.hours === s.snapshotIntervalHours)?.label ??
              `${s.snapshotIntervalHours}시간`}
            {s.editable && (
              <>
                {' '}
                ·{' '}
                <Link
                  to={`/p/${project.id}/collection`}
                  className="underline-offset-2 hover:underline"
                >
                  수집 설정에서 바꾸기
                </Link>
              </>
            )}
          </p>
        )}
      </DataState>

      <DataState state={state} onRetry={state.reload} empty={{ text: '아직 기록이 없습니다.' }}>
        {(rows) => <SnapshotBody rows={rows} />}
      </DataState>
    </>
  );
}

function SnapshotBody({ rows }: { rows: ProgressSnapshotResponse[] }): ReactNode {
  // 서버는 최근 것이 앞. 그래프는 오래된 것부터
  const series = useMemo(() => [...rows].reverse(), [rows]);
  const withDelta = useMemo(
    () =>
      rows.map((r, i) => ({
        row: r,
        prev: rows[i + 1] ?? null, // 표는 최근이 위라 다음 줄이 전날이다
      })),
    [rows],
  );

  if (rows.length === 0) {
    return <p className="text-muted-foreground text-sm">아직 기록이 없습니다.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded border p-4">
        <h2 className="mb-3 text-sm font-semibold">진척률 추이</h2>
        {series.length < 2 ? (
          <p className="text-muted-foreground text-sm">
            기록이 {series.length}건이라 아직 선이 되지 않습니다. 내일부터 이어집니다.
          </p>
        ) : (
          <ChartContainer config={CHART} className="h-64 w-full">
            <LineChart data={series} margin={{ left: 8, right: 16, top: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="snapshotDate" tickFormatter={(v: string) => v.slice(5)} />
              <YAxis domain={[0, 100]} width={36} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Line
                type="monotone"
                dataKey="representativePct"
                stroke="var(--color-representativePct)"
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="wbsPlannedPct"
                stroke="var(--color-wbsPlannedPct)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls
              />
            </LineChart>
          </ChartContainer>
        )}
      </section>

      <section className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-xs">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium">날짜</th>
              <th className="px-4 py-2.5 text-right font-medium">진척률</th>
              <th className="px-4 py-2.5 text-right font-medium">계획</th>
              <th className="px-4 py-2.5 text-right font-medium">편차</th>
              <th className="px-4 py-2.5 text-right font-medium">지연 작업</th>
              <th className="px-4 py-2.5 text-right font-medium">이슈 해결</th>
              <th className="px-4 py-2.5 text-right font-medium">요구사항 검증</th>
              <th className="px-4 py-2.5 text-right font-medium">리스크 종료</th>
              <th className="px-4 py-2.5 text-right font-medium">산출물 제출</th>
              <th className="px-4 py-2.5 text-left font-medium">산정</th>
              <th className="px-4 py-2.5 text-left font-medium">찍은 시각</th>
            </tr>
          </thead>
          <tbody>
            {withDelta.map(({ row: r, prev }) => (
              <tr key={r.snapshotDate} className="border-t">
                <td className="tnum px-4 py-2.5 whitespace-nowrap">{formatDate(r.snapshotDate)}</td>
                <td className="tnum px-4 py-2.5 text-right">
                  <Pct value={r.representativePct} />
                  <Delta
                    now={r.representativePct}
                    prev={prev?.representativePct ?? null}
                    unit="%p"
                  />
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  <Pct value={r.wbsPlannedPct} />
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {r.representativePct !== null && r.wbsPlannedPct !== null ? (
                    <span
                      className={cn(
                        r.representativePct - r.wbsPlannedPct < 0 && 'text-destructive',
                      )}
                    >
                      {(r.representativePct - r.wbsPlannedPct).toFixed(1)}%p
                    </span>
                  ) : (
                    '-'
                  )}
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {r.behindTaskCount}
                  <Delta
                    now={r.behindTaskCount}
                    prev={prev?.behindTaskCount ?? null}
                    unit=""
                    badIsUp
                  />
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {r.issueResolvedCount}/{r.issueTotalCount}
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {r.requirementVerifiedCount}/{r.requirementTotalCount}
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {r.riskClosedCount}/{r.riskTotalCount}
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {r.workProductSubmittedCount}/{r.workProductTotalCount}
                  <Delta
                    now={r.workProductSubmittedCount}
                    prev={prev?.workProductSubmittedCount ?? null}
                    unit=""
                  />
                </td>
                <td className="text-muted-foreground px-4 py-2.5 whitespace-nowrap">
                  {LEVEL_LABEL[r.level] ?? r.level}
                </td>
                <td className="text-muted-foreground tnum px-4 py-2.5 whitespace-nowrap">
                  {formatDateTime(r.createdAt)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Pct({ value }: { value: number | null }): ReactNode {
  return <span>{value === null ? '-' : `${value.toFixed(1)}%`}</span>;
}

/** 전날 대비 변화. 0 이면 안 보인다. badIsUp 이면 늘어난 것이 나쁜 신호다(지연 작업). */
function Delta({
  now,
  prev,
  unit,
  badIsUp = false,
}: {
  now: number | null;
  prev: number | null;
  unit: string;
  badIsUp?: boolean;
}): ReactNode {
  if (now === null || prev === null) return null;
  const d = Math.round((now - prev) * 10) / 10;
  if (d === 0) return null;
  const bad = badIsUp ? d > 0 : d < 0;
  return (
    <span
      className={cn(
        'ml-1.5 text-xs',
        bad ? 'text-destructive' : 'text-emerald-600 dark:text-emerald-300',
      )}
    >
      {d > 0 ? '▲' : '▼'}
      {Math.abs(d)}
      {unit}
    </span>
  );
}
