import { useMemo, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { IssueResponse, IssueStatus, PageResponse } from '@/types/api';

const OPEN_STATES: IssueStatus[] = ['OPEN', 'IN_PROGRESS'];
/** 먼저 봐야 하는 심각도 — 도구마다 이름이 달라 넓게 잡는다. */
const HEAVY = new Set(['BLOCKER', 'CRITICAL', 'HIGH', 'MAJOR']);

export function IssuesPage(): ReactNode {
  const { project } = useProjectContext();

  const state = useAsync<PageResponse<IssueResponse>>(
    () =>
      api.get<PageResponse<IssueResponse>>(
        `/projects/${project.id}/issues${toQueryString({ size: 100 })}`,
      ),
    [project.id],
  );

  const columns = useMemo(() => buildColumns(), []);

  return (
    <>
      <PageHeader title="이슈" />
      <DataState state={state} onRetry={state.reload}>
        {(data) => {
          const all = data.content;
          const open = all.filter((i) => OPEN_STATES.includes(i.status));
          const heavy = open.filter((i) => i.severity !== null && HEAVY.has(i.severity));
          const unassigned = open.filter((i) => !i.assignee);
          const done = all.length - open.length;

          return (
            <div className="@container flex flex-col gap-5">
              <div className="grid grid-cols-2 gap-3 @2xl:grid-cols-4">
                <MetricCard term="열린 이슈" value={open.length} hint={`전체 ${all.length}건`} />
                <MetricCard
                  term="심각·높음"
                  value={heavy.length}
                  hint="열린 것 중"
                  tone={heavy.length > 0 ? 'text-destructive' : undefined}
                />
                <MetricCard
                  term="담당 없음"
                  value={unassigned.length}
                  hint="열린 것 중"
                  tone={unassigned.length > 0 ? 'text-warning' : undefined}
                />
                <MetricCard
                  term="해결·닫힘"
                  value={done}
                  hint={all.length > 0 ? `${Math.round((done / all.length) * 100)}%` : '0%'}
                />
              </div>

              <DataTable<IssueResponse, unknown>
                columns={columns}
                data={all}
                filterColumn="title"
                filterPlaceholder="이슈 제목으로 찾기"
                pageSize={25}
                emptyText="수집된 이슈가 없습니다. 연동을 붙이면 도구의 이슈가 여기 쌓입니다."
              />
            </div>
          );
        }}
      </DataState>
    </>
  );
}

/** 이슈 현황 한 칸. 숫자를 크게 두고 무엇을 센 값인지 아래에 적는다. */
function MetricCard({
  term,
  value,
  hint,
  tone,
}: {
  term: string;
  value: number;
  hint?: string;
  tone?: string;
}): ReactNode {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <p className="win-label truncate">{term}</p>
        <p className={`tnum mt-1 text-2xl font-semibold ${tone ?? 'text-foreground'}`}>{value}</p>
        {hint && (
          <p className="text-muted-foreground text-xs font-semibold tracking-wide mt-0.5">{hint}</p>
        )}
      </CardContent>
    </Card>
  );
}

function buildColumns(): ColumnDef<IssueResponse, unknown>[] {
  return [
    {
      accessorKey: 'key',
      header: ({ column }) => <SortableHeader column={column}>이슈번호</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground font-mono text-xs">{row.original.key}</span>
      ),
    },
    {
      accessorKey: 'title',
      header: ({ column }) => <SortableHeader column={column}>제목</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-md truncate" title={row.original.title}>
          {row.original.title}
        </span>
      ),
    },
    {
      accessorKey: 'severity',
      header: ({ column }) => <SortableHeader column={column}>심각도</SortableHeader>,
      cell: ({ row }) =>
        row.original.severity ? (
          <Badge variant={badgeVariantFor(row.original.severity)}>
            {label(row.original.severity)}
          </Badge>
        ) : (
          '-'
        ),
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
      cell: ({ row }) => (
        <Badge variant={badgeVariantFor(row.original.status)}>{label(row.original.status)}</Badge>
      ),
    },
    {
      accessorKey: 'assignee',
      header: '담당',
      cell: ({ row }) => row.original.assignee ?? '-',
    },
    {
      accessorKey: 'updatedAt',
      header: ({ column }) => <SortableHeader column={column}>수정일</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">{formatDateTime(row.original.updatedAt)}</span>
      ),
    },
    {
      id: 'source',
      header: '원문',
      cell: ({ row }) =>
        row.original.source.externalUrl ? (
          <a
            className="text-primary inline-flex items-center gap-1 hover:underline"
            href={row.original.source.externalUrl}
            target="_blank"
            rel="noreferrer"
          >
            {row.original.source.tool} <ExternalLink className="size-3" />
          </a>
        ) : (
          <span className="text-muted-foreground">{row.original.source.tool}</span>
        ),
    },
  ];
}
