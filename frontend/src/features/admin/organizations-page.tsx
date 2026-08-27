import { useMemo, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { PageHeader } from '@/components/layout/page-header';
import { AccountTable } from '@/features/admin/account-table';
import { OrgCreateDialog } from '@/features/admin/org-create-dialog';
import { UserCreateDialog } from '@/features/admin/user-create-dialog';
import { api } from '@/lib/http';
import { formatDate } from '@/lib/format';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { OrganizationResponse, PageResponse, UserResponse } from '@/types/api';

/** 발주사 하나의 계정 목록. 발주사와 계정을 한 화면에서 관리한다. */
function AccountsDialog({
  organization,
  onClose,
}: {
  organization: OrganizationResponse;
  onClose: () => void;
}): ReactNode {
  const [createOpen, setCreateOpen] = useState(false);
  const state = useAsync<PageResponse<UserResponse>>(
    () =>
      api.get<PageResponse<UserResponse>>(
        `/users${toQueryString({ organizationId: organization.id, size: 100 })}`,
      ),
    [organization.id],
  );

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{organization.name} 계정</DialogTitle>
        </DialogHeader>
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            계정 생성
          </Button>
        </div>
        <DataState state={state} onRetry={state.reload} empty={{ text: '계정이 없습니다.' }}>
          {(data) => <AccountTable users={data.content} />}
        </DataState>
        <UserCreateDialog
          role="CLIENT"
          fixedOrganization={organization}
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={state.reload}
        />
      </DialogContent>
    </Dialog>
  );
}

export function OrganizationsPage(): ReactNode {
  const [page, setPage] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<OrganizationResponse | null>(null);

  const state = useAsync<PageResponse<OrganizationResponse>>(
    () =>
      api.get<PageResponse<OrganizationResponse>>(
        `/organizations${toQueryString({ type: 'CLIENT', page, size: 20 })}`,
      ),
    [page],
  );

  const columns = useMemo(() => buildColumns(setSelected), []);

  return (
    <>
      <PageHeader
        title="발주사"
        description="발주사와 소속 계정을 관리합니다."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            발주사 등록
          </Button>
        }
      />
      <div>
        <DataState state={state} onRetry={state.reload} empty={{ text: '발주사가 없습니다.' }}>
          {(data) => (
            <>
              <DataTable<OrganizationResponse, unknown>
                columns={columns}
                data={data.content}
                filterColumn="name"
                filterPlaceholder="발주사 이름으로 찾기"
                paginated={false}
                emptyText="발주사가 없습니다."
              />
              <PaginationBar page={data} onChange={setPage} />
            </>
          )}
        </DataState>
      </div>

      <OrgCreateDialog
        type="CLIENT"
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={state.reload}
      />
      {selected && (
        <AccountsDialog
          organization={selected}
          onClose={() => {
            setSelected(null);
            state.reload();
          }}
        />
      )}
    </>
  );
}

function buildColumns(
  onManageAccounts: (organization: OrganizationResponse) => void,
): ColumnDef<OrganizationResponse, unknown>[] {
  return [
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column}>이름</SortableHeader>,
    },
    {
      accessorKey: 'businessNo',
      header: '사업자번호',
      cell: ({ row }) => <span className="tnum">{row.original.businessNo ?? '-'}</span>,
    },
    {
      accessorKey: 'userCount',
      header: ({ column }) => <SortableHeader column={column}>계정</SortableHeader>,
      cell: ({ row }) => <span className="tnum">{row.original.userCount}</span>,
    },
    {
      accessorKey: 'projectCount',
      header: ({ column }) => <SortableHeader column={column}>프로젝트</SortableHeader>,
      cell: ({ row }) => <span className="tnum">{row.original.projectCount}</span>,
    },
    {
      accessorKey: 'createdAt',
      header: ({ column }) => <SortableHeader column={column}>등록일</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">{formatDate(row.original.createdAt)}</span>
      ),
    },
    {
      id: 'manage',
      header: '',
      cell: ({ row }) => (
        <Button size="sm" variant="outline" onClick={() => onManageAccounts(row.original)}>
          계정 관리
        </Button>
      ),
    },
  ];
}
