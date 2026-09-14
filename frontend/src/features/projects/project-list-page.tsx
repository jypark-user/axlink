import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SearchInput } from '@/components/ui/search-input';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { PageHeader } from '@/components/layout/page-header';
import { useAuth } from '@/features/auth/auth-context';
import { ProjectCreateDialog } from '@/features/projects/project-create-dialog';
import { api } from '@/lib/http';
import { formatPeriod } from '@/lib/format';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { PageResponse, ProjectSummaryResponse, Role } from '@/types/api';

export function ProjectListPage(): ReactNode {
  const { me } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  const [page, setPage] = useState(0);

  const state = useAsync<PageResponse<ProjectSummaryResponse>>(
    () =>
      api.get<PageResponse<ProjectSummaryResponse>>(
        `/projects${toQueryString({ q: term || null, page, size: 20 })}`,
      ),
    [term, page],
  );

  return (
    <>
      <PageHeader
        title="사업 목록"
        description="참여 중인 사업 목록입니다."
        actions={
          me?.role === 'CLIENT' ? (
            <Button onClick={() => setCreateOpen(true)}>사업 등록</Button>
          ) : null
        }
      />
      {me?.role === 'CLIENT' && (
        <ProjectCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
      )}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-4 md:px-6">
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setTerm(q.trim());
            setPage(0);
          }}
        >
          <SearchInput
            className="w-56"
            placeholder="사업명 검색"
            aria-label="사업명 검색"
            value={q}
            onValueChange={setQ}
          />
          <Button type="submit" variant="outline">
            검색
          </Button>
        </form>
      </div>
      <div>
        <DataState state={state} onRetry={state.reload} empty={{ text: '표시할 사업이 없습니다.' }}>
          {(data) =>
            data.content.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                조건에 맞는 사업이 없습니다.
              </p>
            ) : (
              <>
                <DataTable<ProjectSummaryResponse, unknown>
                  columns={projectColumns(me?.role)}
                  data={data.content}
                  paginated={false}
                  emptyText="조건에 맞는 사업이 없습니다."
                />
                <PaginationBar page={data} onChange={setPage} />
              </>
            )
          }
        </DataState>
      </div>
    </>
  );
}

/**
 * 늘 같은 값인 칸은 두지 않는다 — 발주사가 보면 발주사 칸이, 용역사가 보면 용역사 칸이
 * 모든 줄에서 자기 조직이라 자리만 차지한다. 여러 조직을 보는 관리자만 둘 다 본다.
 */
function projectColumns(role: Role | undefined): ColumnDef<ProjectSummaryResponse, unknown>[] {
  const columns: ColumnDef<ProjectSummaryResponse, unknown>[] = [
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column}>사업명</SortableHeader>,
      cell: ({ row }) => (
        <Link to={`/p/${row.original.id}`} className="font-medium hover:underline">
          {row.original.name}
        </Link>
      ),
    },
    {
      accessorKey: 'endDate',
      header: ({ column }) => <SortableHeader column={column}>사업 기간</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">
          {formatPeriod(row.original.startDate, row.original.endDate)}
        </span>
      ),
    },
  ];

  if (role !== 'CLIENT') {
    columns.push({
      accessorKey: 'clientOrgName',
      header: '발주사',
      cell: ({ row }) => row.original.clientOrgName,
    });
  }

  if (role !== 'CONTRACTOR') {
    columns.push({
      id: 'contractors',
      header: '용역사',
      // 사업 등록에서 입력한 이름 그대로. 연결된 계정에서 캐 오지 않는다.
      cell: ({ row }) =>
        row.original.contractorName ? (
          <span className="truncate">{row.original.contractorName}</span>
        ) : (
          <span className="text-muted-foreground">-</span>
        ),
    });
  }

  columns.push({
    id: 'alerts',
    header: '이슈',
    cell: ({ row }) => {
      const {
        openCorrectionActionCount: ca,
        openRiskCount: risk,
        openReviewRequestCount: req,
      } = row.original;
      if (ca === 0 && risk === 0 && req === 0) {
        return <span className="text-muted-foreground">-</span>;
      }
      return (
        <div className="flex flex-wrap gap-1.5">
          {req > 0 && <Badge variant="primary">요청 {req}</Badge>}
          {ca > 0 && <Badge variant="destructive">시정 {ca}</Badge>}
          {risk > 0 && <Badge variant="warning">리스크 {risk}</Badge>}
        </div>
      );
    },
  });

  return columns;
}
