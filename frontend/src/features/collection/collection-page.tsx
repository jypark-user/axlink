import { useEffect, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { PageHeader } from '@/components/layout/page-header';
import { ScheduleSettingsDialog } from '@/features/collection/schedule-settings-dialog';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import type { PageResponse, SyncJobResponse, ToolConnectionResponse } from '@/types/api';

const POLL_MS = 30_000;
const ALL = 'ALL';
const STATUSES = ['SUCCEEDED', 'FAILED', 'RUNNING', 'QUEUED', 'CANCELLED'] as const;

const elapsed = (job: SyncJobResponse): string => {
  if (!job.startedAt) return '-';
  const end = job.finishedAt ? new Date(job.finishedAt) : new Date();
  const sec = Math.max(0, Math.round((end.getTime() - new Date(job.startedAt).getTime()) / 1000));
  return `${sec}초`;
};

const NUM_COL = 'w-16 text-right whitespace-nowrap';

const statColumn = (
  key: keyof SyncJobResponse['stats'],
  title: string,
  tone?: (n: number) => string | undefined,
): ColumnDef<SyncJobResponse, unknown> => ({
  id: key,
  header: title,
  meta: { className: NUM_COL },
  cell: ({ row }) => {
    const n = Number(row.original.stats[key] ?? 0);
    return <span className={cn('tnum', tone?.(n))}>{n}</span>;
  },
});

const jobColumns = (reload: () => void): ColumnDef<SyncJobResponse, unknown>[] => [
  {
    accessorKey: 'connectionName',
    header: ({ column }) => <SortableHeader column={column}>연결</SortableHeader>,
    cell: ({ row }) => (
      <span className="block max-w-56 truncate" title={row.original.connectionName}>
        {row.original.connectionName}
      </span>
    ),
  },
  {
    accessorKey: 'kind',
    header: '종류',
    cell: ({ row }) => label(row.original.kind),
  },
  {
    accessorKey: 'status',
    header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
    cell: ({ row }) => (
      <Badge variant={badgeVariantFor(row.original.status)}>{label(row.original.status)}</Badge>
    ),
  },
  // 수집 수치는 한 칸에 몰아 두면 읽기 어려워 네 칸으로 나눴다(11-20). 숫자만 들어가 폭을 좁힌다
  statColumn('fetched', '수집'),
  statColumn('upserted', '반영'),
  statColumn('unmapped', '미매핑', (n) => (n > 0 ? 'text-warning' : undefined)),
  statColumn('indexed', '색인'),
  {
    id: 'elapsed',
    header: '소요',
    cell: ({ row }) => <span className="tnum">{elapsed(row.original)}</span>,
  },
  {
    accessorKey: 'startedAt',
    header: ({ column }) => <SortableHeader column={column}>시작</SortableHeader>,
    cell: ({ row }) => (
      <span className="text-muted-foreground tnum">
        {row.original.startedAt ? formatDateTime(row.original.startedAt) : '-'}
      </span>
    ),
  },
  {
    id: 'actions',
    header: '',
    cell: ({ row }) =>
      row.original.retryable ? (
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="outline"
            onClick={() => api.post(`/sync-jobs/${row.original.id}/retry`, {}).finally(reload)}
          >
            재시도
          </Button>
        </div>
      ) : null,
  },
];

export function CollectionPage(): ReactNode {
  const { project } = useProjectContext();
  const [page, setPage] = useState(0);
  // 연결·상태·시작 기간 필터(11-20). 쪽을 넘기므로 서버가 거른다. 바꾸면 첫 쪽으로 돌아간다
  const [connectionId, setConnectionId] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const filtered = connectionId !== ALL || status !== ALL || from !== '' || to !== '';
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v);
      setPage(0);
    };
  const connections = useAsync<ToolConnectionResponse[]>(
    () => api.get<ToolConnectionResponse[]>(`/projects/${project.id}/connections`),
    [project.id],
  );
  const state = useAsync<PageResponse<SyncJobResponse>>(
    () =>
      api.get<PageResponse<SyncJobResponse>>(
        `/sync-jobs${toQueryString({
          projectId: project.id,
          page,
          size: 20,
          connectionId: connectionId === ALL ? undefined : connectionId,
          status: status === ALL ? undefined : status,
          startedFrom: from || undefined,
          startedTo: to || undefined,
        })}`,
      ),
    [project.id, page, connectionId, status, from, to],
  );
  const { reload } = state;

  useEffect(() => {
    const timer = window.setInterval(reload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [reload]);

  return (
    <>
      <PageHeader
        title="동기화"
        description="도구에서 가져온 수집 잡 이력입니다. 30초마다 자동 갱신됩니다."
        actions={
          <>
            <ScheduleSettingsDialog projectId={project.id} part="sync" onSaved={reload} />
            <Button size="sm" variant="outline" onClick={reload}>
              새로고침
            </Button>
          </>
        }
      />
      <div className="flex flex-wrap items-center gap-2 pb-3">
        <Select value={connectionId} onValueChange={reset(setConnectionId)}>
          <SelectTrigger className="w-56" aria-label="연결로 거르기">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>전체 연결</SelectItem>
            {(connections.data ?? []).map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={reset(setStatus)}>
          <SelectTrigger className="w-32" aria-label="상태로 거르기">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>전체 상태</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {label(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-1.5">
          <Input
            type="date"
            className="w-40"
            value={from}
            max={to || undefined}
            onChange={(e) => reset(setFrom)(e.target.value)}
            aria-label="시작일부터"
          />
          <span className="text-muted-foreground text-sm">~</span>
          <Input
            type="date"
            className="w-40"
            value={to}
            min={from || undefined}
            onChange={(e) => reset(setTo)(e.target.value)}
            aria-label="시작일까지"
          />
        </div>
        {filtered && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setConnectionId(ALL);
              setStatus(ALL);
              setFrom('');
              setTo('');
              setPage(0);
            }}
          >
            필터 지우기
          </Button>
        )}
      </div>
      <DataState
        state={state}
        onRetry={reload}
        empty={{ text: filtered ? '조건에 맞는 수집 이력이 없습니다.' : '수집 이력이 없습니다.' }}
      >
        {(data) => (
          <>
            <DataTable<SyncJobResponse, unknown>
              columns={jobColumns(reload)}
              data={data.content}
              paginated={false}
              emptyText="수집 이력이 없습니다."
            />
            {data.content.some((j) => j.error) && (
              <div className="mt-4 flex flex-col gap-2">
                {data.content
                  .filter((j) => j.error)
                  .map((j) => (
                    <p
                      key={j.id}
                      className="whitespace-pre-wrap rounded bg-destructive/10 p-2 font-mono text-xs text-destructive"
                    >
                      {j.connectionName}: {j.error}
                    </p>
                  ))}
              </div>
            )}
            <PaginationBar page={data} onChange={setPage} />
          </>
        )}
      </DataState>
    </>
  );
}
