import { useMemo, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import type { UserInviteLinkResponse, UserResponse } from '@/types/api';

export function AccountTable({
  users,
  organizationHeader,
}: {
  users: UserResponse[];
  /** 소속 열 제목. 주지 않으면 소속 열을 숨긴다. */
  organizationHeader?: string;
}): ReactNode {
  const { toast } = useToast();

  // 발송하지 않는다. 링크를 만들어 클립보드에 넣어 주면 관리자가 알아서 전달한다.
  const copyInviteLink = async (userId: string) => {
    try {
      const { token } = await api.post<UserInviteLinkResponse>(
        `/users/${userId}/invitation-link`,
        {},
      );
      const url = `${window.location.origin}/invite/accept?token=${encodeURIComponent(token)}`;
      await navigator.clipboard.writeText(url);
      toast({ title: '초대 링크를 복사했습니다.', description: url, variant: 'success' });
    } catch (err) {
      toast({
        title: '초대 링크 생성에 실패했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  const columns = useMemo(
    // copyInviteLink 는 스스로 오류를 알린다 — 반환 Promise 는 여기서 버린다.
    () => buildColumns(organizationHeader, (...args) => void copyInviteLink(...args)),
    // copyInviteLink 는 렌더마다 새로 만들어지지만 표는 열 정의만 보면 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [organizationHeader],
  );

  return (
    <DataTable<UserResponse, unknown>
      columns={columns}
      data={users}
      paginated={false}
      emptyText="계정이 없습니다."
    />
  );
}

function buildColumns(
  organizationHeader: string | undefined,
  copyInviteLink: (userId: string) => void,
): ColumnDef<UserResponse, unknown>[] {
  const columns: ColumnDef<UserResponse, unknown>[] = [
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column}>이름</SortableHeader>,
    },
    {
      accessorKey: 'username',
      header: ({ column }) => <SortableHeader column={column}>아이디</SortableHeader>,
    },
  ];

  if (organizationHeader) {
    columns.push({
      accessorKey: 'organizationName',
      header: ({ column }) => <SortableHeader column={column}>{organizationHeader}</SortableHeader>,
    });
  }

  columns.push(
    {
      accessorKey: 'status',
      header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
      cell: ({ row }) => (
        <Badge variant={badgeVariantFor(row.original.status)}>{label(row.original.status)}</Badge>
      ),
    },
    {
      accessorKey: 'lastLoginAt',
      header: ({ column }) => <SortableHeader column={column}>마지막 로그인</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">
          {row.original.lastLoginAt ? formatDateTime(row.original.lastLoginAt) : '-'}
        </span>
      ),
    },
    {
      id: 'invite',
      header: '',
      cell: ({ row }) =>
        row.original.status === 'INVITED' ? (
          <Button size="sm" variant="outline" onClick={() => copyInviteLink(row.original.id)}>
            초대 링크 복사
          </Button>
        ) : null,
    },
  );

  return columns;
}
