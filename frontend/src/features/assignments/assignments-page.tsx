import { useMemo, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { InviteLinkDialog } from '@/features/assignments/invite-link-dialog';
import { ParticipantsPanel } from '@/features/assignments/participants-panel';
import type { AssignmentResponse, ParticipantResponse } from '@/types/api';

/** `embedded` 면 사업 정보 화면 안에 들어간다 — 자체 화면 머리를 두지 않는다. */
export function AssignmentsPage({ embedded }: { embedded?: boolean } = {}): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<AssignmentResponse | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const columns = useMemo(() => buildColumns(setRevokeTarget, pendingId), [pendingId]);

  const state = useAsync<AssignmentResponse[]>(
    () => api.get<AssignmentResponse[]>(`/projects/${project.id}/assignments`),
    [project.id],
  );
  const parts = useAsync<ParticipantResponse[]>(
    () => api.get<ParticipantResponse[]>(`/projects/${project.id}/participants`),
    [project.id],
  );

  const revoke = async (assignment: AssignmentResponse) => {
    setPendingId(assignment.id);
    try {
      await api.del<void>(`/projects/${project.id}/assignments/${assignment.id}`);
      toast({ title: '할당을 해제했습니다.', variant: 'success' });
      state.reload();
    } catch (e) {
      toast({
        title: '해제에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setPendingId(null);
      setRevokeTarget(null);
    }
  };

  const addButton = (
    <Button size="sm" onClick={() => setInviteOpen(true)}>
      초대 링크 만들기
    </Button>
  );

  return (
    <>
      {embedded ? (
        <div className="flex justify-end pb-3">{addButton}</div>
      ) : (
        <PageHeader
          title="용역사"
          description="초대 링크를 전달하면 용역사가 직접 계정을 만들고 이 사업에 참여합니다."
          actions={addButton}
        />
      )}
      {parts.data && (
        <div className="pb-4">
          <ParticipantsPanel
            projectId={project.id}
            rows={parts.data}
            onChanged={(next) => {
              parts.setData(next);
              state.reload();
            }}
          />
        </div>
      )}
      <DataState
        state={state}
        onRetry={state.reload}
        skeleton={
          <div className="flex flex-col gap-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        }
        empty={{ text: '아직 참여한 용역사가 없습니다. 초대 링크를 만들어 전달하세요.' }}
      >
        {(rows) => (
          <DataTable<AssignmentResponse, unknown>
            columns={columns}
            data={rows}
            paginated={false}
            emptyText="아직 참여한 용역사가 없습니다."
          />
        )}
      </DataState>

      <InviteLinkDialog
        projectId={project.id}
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        participants={parts.data ?? []}
      />

      <AlertDialog
        open={revokeTarget !== null}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>할당을 해제할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              {revokeTarget?.userName} ({revokeTarget?.userEmail}) 계정이 이 프로젝트에 접근할 수
              없게 됩니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => revokeTarget && void revoke(revokeTarget)}
              disabled={pendingId !== null}
            >
              해제
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function buildColumns(
  onRevoke: (assignment: AssignmentResponse) => void,
  pendingId: string | null,
): ColumnDef<AssignmentResponse, unknown>[] {
  return [
    {
      accessorKey: 'contractorOrgName',
      header: ({ column }) => <SortableHeader column={column}>용역사</SortableHeader>,
      cell: ({ row }) => <span className="font-medium">{row.original.contractorOrgName}</span>,
    },
    {
      id: 'account',
      accessorFn: (a) => `${a.userName} ${a.userEmail}`,
      header: '계정',
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span>{row.original.userName}</span>
          <span className="text-muted-foreground text-xs">{row.original.userEmail}</span>
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
      cell: ({ row }) => {
        const active = row.original.status === 'ACTIVE';
        return <Badge variant={active ? 'success' : 'outline'}>{active ? '활성' : '해제됨'}</Badge>;
      },
    },
    {
      accessorKey: 'assignedAt',
      header: ({ column }) => <SortableHeader column={column}>할당일</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">
          {formatDateTime(row.original.assignedAt)}
        </span>
      ),
    },
    {
      id: 'revoke',
      header: '',
      cell: ({ row }) =>
        row.original.status === 'ACTIVE' ? (
          <Button
            size="sm"
            variant="outline"
            disabled={pendingId === row.original.id}
            onClick={() => onRevoke(row.original)}
          >
            해제
          </Button>
        ) : null,
    },
  ];
}
