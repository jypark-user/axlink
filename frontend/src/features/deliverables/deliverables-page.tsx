import { useMemo, useState, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import type { WorkProductChecklistResponse, WorkProductResponse } from '@/types/api';

/** 산출물은 사업 관리(PM)와 구현(SI) 활동으로 갈린다 — 그 갈래를 탭으로 둔다. */
type Category = 'ALL' | 'PM' | 'SI';

const CATEGORIES: { key: Category; label: string }[] = [
  { key: 'ALL', label: '전체' },
  { key: 'PM', label: '사업 관리' },
  { key: 'SI', label: '구현' },
];

const inCategory = (wp: WorkProductResponse, category: Category): boolean => {
  if (category === 'ALL') return true;
  if (category === 'PM') return wp.pmActivity !== null;
  return wp.siActivity !== null;
};

export function DeliverablesPage(): ReactNode {
  const { project } = useProjectContext();
  const [category, setCategory] = useState<Category>('ALL');

  const state = useAsync<WorkProductChecklistResponse>(
    () => api.get<WorkProductChecklistResponse>(`/projects/${project.id}/work-products`),
    [project.id],
  );

  const columns = useMemo(() => buildColumns(), []);

  return (
    <>
      <PageHeader title="산출물" />
      <DataState state={state} onRetry={state.reload}>
        {(data) => {
          const rows = data.items.filter((wp) => inCategory(wp, category));
          return (
            <Tabs value={category} onValueChange={(next) => setCategory(next as Category)}>
              <TabsList>
                {CATEGORIES.map((tab) => (
                  <TabsTrigger key={tab.key} value={tab.key}>
                    {tab.label}
                    <span className="text-muted-foreground text-xs font-semibold tracking-wide tnum ml-1.5">
                      {data.items.filter((wp) => inCategory(wp, tab.key)).length}
                    </span>
                  </TabsTrigger>
                ))}
              </TabsList>

              <DataTable<WorkProductResponse, unknown>
                columns={columns}
                data={rows}
                filterColumn="title"
                filterPlaceholder="산출물 이름으로 찾기"
                pageSize={25}
                emptyText="산출물이 없습니다."
                className="mt-4"
              />
            </Tabs>
          );
        }}
      </DataState>
    </>
  );
}

function buildColumns(): ColumnDef<WorkProductResponse, unknown>[] {
  return [
    {
      accessorKey: 'type',
      header: ({ column }) => <SortableHeader column={column}>유형</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground font-mono text-xs">{row.original.type}</span>
      ),
    },
    {
      id: 'title',
      accessorFn: (wp) => wp.title ?? wp.displayName,
      header: ({ column }) => <SortableHeader column={column}>제목</SortableHeader>,
      cell: ({ row }) => (
        <span
          className={row.original.applicable ? 'text-foreground' : 'text-muted-foreground/60'}
          title={row.original.title ?? row.original.displayName}
        >
          {row.original.title ?? row.original.displayName}
        </span>
      ),
    },
    {
      accessorKey: 'version',
      header: '버전',
      cell: ({ row }) => <span className="tnum">{row.original.version ?? '-'}</span>,
    },
    {
      id: 'activity',
      accessorFn: (wp) => wp.pmActivity ?? wp.siActivity ?? '',
      header: '활동',
      cell: ({ row }) => row.original.pmActivity ?? row.original.siActivity ?? '-',
    },
    {
      accessorKey: 'dueDate',
      header: ({ column }) => <SortableHeader column={column}>기한</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">
          {row.original.dueDate ? formatDate(row.original.dueDate) : '-'}
        </span>
      ),
    },
    {
      // 최신 버전을 가리는 기준. 상태 전이는 이 화면에서 다루지 않는다 — 도구에서 수집한 값을 보여 준다.
      accessorKey: 'updatedAt',
      header: ({ column }) => <SortableHeader column={column}>수정일</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">{formatDateTime(row.original.updatedAt)}</span>
      ),
    },
  ];
}
