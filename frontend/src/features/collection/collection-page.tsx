import { useEffect, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import type { PageResponse, SyncJobResponse } from '@/types/api';

const POLL_MS = 30_000;

const elapsed = (job: SyncJobResponse): string => {
  if (!job.startedAt) return '-';
  const end = job.finishedAt ? new Date(job.finishedAt) : new Date();
  const sec = Math.max(0, Math.round((end.getTime() - new Date(job.startedAt).getTime()) / 1000));
  return `${sec}초`;
};

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
  {
    id: 'stats',
    header: '수집/반영/미매핑/색인',
    cell: ({ row }) => {
      const s = row.original.stats;
      return (
        <span className="tnum">
          {s.fetched}/{s.upserted}/
          <span className={s.unmapped > 0 ? 'text-warning' : undefined}>{s.unmapped}</span>/
          {s.indexed}
        </span>
      );
    },
  },
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
  const state = useAsync<PageResponse<SyncJobResponse>>(
    () =>
      api.get<PageResponse<SyncJobResponse>>(
        `/sync-jobs${toQueryString({ projectId: project.id, page, size: 20 })}`,
      ),
    [project.id, page],
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
            <ScheduleSettingsDialog projectId={project.id} onSaved={reload} />
            <Button size="sm" variant="outline" onClick={reload}>
              새로고침
            </Button>
          </>
        }
      />
      <DataState state={state} onRetry={reload} empty={{ text: '수집 이력이 없습니다.' }}>
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
