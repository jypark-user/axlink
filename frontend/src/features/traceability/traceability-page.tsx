import { useMemo, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { badgeVariantFor, label } from '@/lib/labels';
import { toQueryString } from '@/lib/query';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import type { PageResponse, TraceCell, TraceLinkKind, TraceabilityRowResponse } from '@/types/api';

export function TraceabilityPage(): ReactNode {
  const { project } = useProjectContext();
  const [page, setPage] = useState(0);
  const state = useAsync<PageResponse<TraceabilityRowResponse>>(
    () =>
      api.get<PageResponse<TraceabilityRowResponse>>(
        `/projects/${project.id}/traceability${toQueryString({ page, size: 20 })}`,
      ),
    [project.id, page],
  );

  const columns = useMemo(() => buildColumns(), []);

  return (
    <>
      <PageHeader
        title="추적표"
        description="요구사항 → 설계 · 구현 · 시험 연결 상태입니다. 끊긴 칸은 붉게 표시됩니다."
      />
      <DataState state={state} onRetry={state.reload} empty={{ text: '요구사항이 없습니다.' }}>
        {(data) => (
          <>
            <DataTable<TraceabilityRowResponse, unknown>
              columns={columns}
              data={data.content}
              filterColumn="requirementTitle"
              filterPlaceholder="요구사항으로 찾기"
              paginated={false}
              emptyText="요구사항이 없습니다."
            />
            <PaginationBar page={data} onChange={setPage} />
          </>
        )}
      </DataState>
    </>
  );
}

function buildColumns(): ColumnDef<TraceabilityRowResponse, unknown>[] {
  return [
    {
      accessorKey: 'requirementCode',
      header: ({ column }) => <SortableHeader column={column}>코드</SortableHeader>,
      cell: ({ row }) => <span className="font-mono text-xs">{row.original.requirementCode}</span>,
    },
    {
      accessorKey: 'requirementTitle',
      header: ({ column }) => <SortableHeader column={column}>요구사항</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-sm truncate" title={row.original.requirementTitle}>
          {row.original.requirementTitle}
        </span>
      ),
    },
    {
      accessorKey: 'requirementStatus',
      header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
      cell: ({ row }) => (
        <Badge variant={badgeVariantFor(row.original.requirementStatus)}>
          {label(row.original.requirementStatus)}
        </Badge>
      ),
    },
    {
      id: 'designs',
      header: '설계',
      cell: ({ row }) => (
        <Cells cells={row.original.designs} kind="DESIGNS" broken={row.original.brokenAt} />
      ),
    },
    {
      id: 'implements',
      header: '구현',
      cell: ({ row }) => (
        <Cells
          cells={row.original.implementsList}
          kind="IMPLEMENTS"
          broken={row.original.brokenAt}
        />
      ),
    },
    {
      id: 'tests',
      header: '시험',
      cell: ({ row }) => (
        <Cells cells={row.original.tests} kind="TESTS" broken={row.original.brokenAt} />
      ),
    },
  ];
}

/** 표 뼈대는 DataTable 이 만든다 — 여기서는 칸 안쪽만 그린다. */
function Cells({
  cells,
  kind,
  broken,
}: {
  cells: TraceCell[];
  kind: TraceLinkKind;
  broken: TraceLinkKind[];
}): ReactNode {
  const isBroken = broken.includes(kind);
  return (
    <div className={cn('-mx-2 px-2 py-1', isBroken && 'bg-destructive/10')}>
      {cells.length === 0 ? (
        <span className="text-muted-foreground text-xs">없음</span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {cells.map((c) => (
            <Badge key={c.targetId} variant="outline" className="max-w-40 truncate">
              {c.externalUrl ? (
                <a
                  className="inline-flex items-center gap-1 hover:underline"
                  href={c.externalUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {c.label} <ExternalLink className="size-3" />
                </a>
              ) : (
                c.label
              )}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
