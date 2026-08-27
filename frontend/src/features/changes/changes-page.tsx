import { useMemo, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDate } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { useAsync } from '@/lib/use-async';
import type {
  ChangeRequestResponse,
  ChangeRequestStatus,
  CorrectionActionResponse,
  CorrectionActionStatus,
  PageResponse,
} from '@/types/api';

function buildCrColumns(
  move: (id: string, next: ChangeRequestStatus) => void,
): ColumnDef<ChangeRequestResponse, unknown>[] {
  return [
    {
      accessorKey: 'code',
      header: ({ column }) => <SortableHeader column={column}>코드</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground font-mono text-xs">{row.original.code}</span>
      ),
    },
    {
      accessorKey: 'title',
      header: ({ column }) => <SortableHeader column={column}>제목</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-xs truncate" title={row.original.title}>
          {row.original.title}
        </span>
      ),
    },
    {
      accessorKey: 'reason',
      header: '사유',
      cell: ({ row }) => (
        <span className="text-muted-foreground block max-w-xs truncate" title={row.original.reason}>
          {row.original.reason}
        </span>
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
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          {CR_NEXT[row.original.status].map((next) => (
            <Button
              key={next}
              size="sm"
              variant="outline"
              onClick={() => move(row.original.id, next)}
            >
              {label(next)}
            </Button>
          ))}
        </div>
      ),
    },
  ];
}

function buildCaColumns(
  move: (id: string, next: CorrectionActionStatus) => void,
): ColumnDef<CorrectionActionResponse, unknown>[] {
  return [
    {
      accessorKey: 'code',
      header: ({ column }) => <SortableHeader column={column}>코드</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground font-mono text-xs">{row.original.code}</span>
      ),
    },
    {
      accessorKey: 'finding',
      header: ({ column }) => <SortableHeader column={column}>제목</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-xs truncate" title={row.original.finding}>
          {row.original.finding}
        </span>
      ),
    },
    {
      accessorKey: 'action',
      header: '내용',
      cell: ({ row }) => (
        <span className="text-muted-foreground block max-w-xs truncate" title={row.original.action}>
          {row.original.action}
        </span>
      ),
    },
    {
      accessorKey: 'owner',
      header: '담당',
      cell: ({ row }) => row.original.owner ?? '-',
    },
    {
      accessorKey: 'dueDate',
      header: ({ column }) => <SortableHeader column={column}>기한</SortableHeader>,
      cell: ({ row }) => (
        <span className="tnum">
          {row.original.dueDate ? formatDate(row.original.dueDate) : '-'}
          {row.original.overdueDays > 0 && (
            <Badge variant="destructive" className="ml-1">
              {row.original.overdueDays}일 지연
            </Badge>
          )}
        </span>
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
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          {CA_NEXT[row.original.status].map((next) => (
            <Button
              key={next}
              size="sm"
              variant="outline"
              onClick={() => move(row.original.id, next)}
            >
              {label(next)}
            </Button>
          ))}
        </div>
      ),
    },
  ];
}

const CR_NEXT: Record<ChangeRequestStatus, ChangeRequestStatus[]> = {
  REQUESTED: ['REVIEWING', 'REJECTED'],
  REVIEWING: ['APPROVED', 'REJECTED'],
  APPROVED: ['APPLIED'],
  REJECTED: [],
  APPLIED: [],
};

const CA_NEXT: Record<CorrectionActionStatus, CorrectionActionStatus[]> = {
  OPEN: ['DONE'],
  OVERDUE: ['DONE'],
  DONE: [],
};

export function ChangesPage({ tab }: { tab: 'CR' | 'CA' }): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();

  const crState = useAsync<PageResponse<ChangeRequestResponse>>(
    () =>
      api.get<PageResponse<ChangeRequestResponse>>(
        `/projects/${project.id}/change-requests?size=50`,
      ),
    [project.id],
  );
  const caState = useAsync<PageResponse<CorrectionActionResponse>>(
    () =>
      api.get<PageResponse<CorrectionActionResponse>>(
        `/projects/${project.id}/correction-actions?size=50`,
      ),
    [project.id],
  );

  const transit = async (path: string, status: string, reload: () => void) => {
    try {
      await api.patch(path, { status, note: null });
      toast({ title: '상태를 변경했습니다.', variant: 'success' });
      reload();
    } catch (e) {
      toast({
        title: '상태 변경에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    }
  };

  const crColumns = useMemo(
    () =>
      buildCrColumns((id, next) => {
        void transit(`/change-requests/${id}/status`, next, crState.reload);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [crState.reload],
  );
  const caColumns = useMemo(
    () =>
      buildCaColumns((id, next) => {
        void transit(`/correction-actions/${id}/status`, next, caState.reload);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [caState.reload],
  );

  return (
    <>
      {tab === 'CR' ? (
        <PageHeader title="변경 요청" description="변경요청을 접수하고 승인 상태를 관리합니다." />
      ) : (
        <PageHeader
          title="시정조치"
          description="연동한 도구의 시정조치 항목을 모아 이행 상태를 관리합니다."
        />
      )}

      {tab === 'CR' ? (
        <DataState
          state={crState}
          onRetry={crState.reload}
          empty={{ text: '변경요청이 없습니다.' }}
        >
          {(data) => (
            <DataTable<ChangeRequestResponse, unknown>
              columns={crColumns}
              data={data.content}
              filterColumn="title"
              filterPlaceholder="제목으로 찾기"
              emptyText="변경요청이 없습니다."
            />
          )}
        </DataState>
      ) : (
        <DataState
          state={caState}
          onRetry={caState.reload}
          empty={{ text: '시정조치가 없습니다.' }}
        >
          {(data) => (
            <DataTable<CorrectionActionResponse, unknown>
              columns={caColumns}
              data={data.content}
              filterColumn="finding"
              filterPlaceholder="제목으로 찾기"
              emptyText="시정조치가 없습니다."
            />
          )}
        </DataState>
      )}
    </>
  );
}
