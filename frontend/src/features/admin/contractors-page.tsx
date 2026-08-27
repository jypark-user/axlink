import { useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { DataState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { PageHeader } from '@/components/layout/page-header';
import { AccountTable } from '@/features/admin/account-table';
import { OrgCreateDialog } from '@/features/admin/org-create-dialog';
import { UserCreateDialog } from '@/features/admin/user-create-dialog';
import { api } from '@/lib/http';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { OrganizationResponse, PageResponse, UserResponse } from '@/types/api';

export function ContractorsPage(): ReactNode {
  const [page, setPage] = useState(0);
  const [orgOpen, setOrgOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  const orgs = useAsync<PageResponse<OrganizationResponse>>(
    () =>
      api.get<PageResponse<OrganizationResponse>>(
        `/organizations${toQueryString({ type: 'CONTRACTOR', size: 100 })}`,
      ),
    [],
  );
  const state = useAsync<PageResponse<UserResponse>>(
    () =>
      api.get<PageResponse<UserResponse>>(
        `/users${toQueryString({ role: 'CONTRACTOR', page, size: 20 })}`,
      ),
    [page],
  );

  return (
    <>
      <PageHeader
        title="용역사 계정"
        description="용역사 소속 계정을 관리합니다."
        actions={
          <>
            <Button size="sm" variant="outline" onClick={() => setOrgOpen(true)}>
              용역사 등록
            </Button>
            <Button size="sm" onClick={() => setUserOpen(true)}>
              계정 생성
            </Button>
          </>
        }
      />
      <div>
        <DataState state={state} onRetry={state.reload} empty={{ text: '용역사 계정이 없습니다.' }}>
          {(data) => (
            <>
              <AccountTable users={data.content} organizationHeader="용역사" />
              <PaginationBar page={data} onChange={setPage} />
            </>
          )}
        </DataState>
      </div>

      <OrgCreateDialog
        type="CONTRACTOR"
        open={orgOpen}
        onOpenChange={setOrgOpen}
        onCreated={orgs.reload}
      />
      <UserCreateDialog
        role="CONTRACTOR"
        organizations={orgs.data?.content ?? []}
        open={userOpen}
        onOpenChange={setUserOpen}
        onCreated={state.reload}
      />
    </>
  );
}
