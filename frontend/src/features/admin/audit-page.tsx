import { useMemo, useState, type FormEvent, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState, EmptyState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { PageHeader } from '@/components/layout/page-header';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import type { EntityHistoryResponse, PageResponse } from '@/types/api';

const ENTITY_TYPES = [
  'PROJECT',
  'PROJECT_ASSIGNMENT',
  'ORGANIZATION',
  'APP_USER',
  'TOOL_CONNECTION',
  'REQUIREMENT',
  'ISSUE',
  'WORK_PRODUCT',
  'RISK',
  'CODE_CHANGE',
  'TRACE_LINK',
  'CHANGE_REQUEST',
  'CORRECTION_ACTION',
  'PROGRESS_RECORD',
  'ACCEPTANCE_RECORD',
  'DOCUMENT_UPLOAD',
] as const;

export function AuditPage(): ReactNode {
  const [entityType, setEntityType] = useState<string>('PROJECT');
  const [entityId, setEntityId] = useState('');
  const [query, setQuery] = useState<{ entityType: string; entityId: string } | null>(null);
  const [page, setPage] = useState(0);
  const columns = useMemo(() => buildColumns(), []);

  const state = useAsync<PageResponse<EntityHistoryResponse> | null>(
    () =>
      query
        ? api.get<PageResponse<EntityHistoryResponse>>(
            `/entity-history${toQueryString({ ...query, page, size: 20 })}`,
          )
        : Promise.resolve(null),
    [query, page],
  );

  const search = (e: FormEvent) => {
    e.preventDefault();
    if (!entityId.trim()) return;
    setPage(0);
    setQuery({ entityType, entityId: entityId.trim() });
  };

  return (
    <>
      <PageHeader title="감사 로그" description="엔터티 종류와 ID 를 모두 지정해야 조회됩니다." />
      <div className="flex flex-col gap-4">
        <form onSubmit={search} className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="entityType">엔터티 종류</Label>
            <Select value={entityType} onValueChange={setEntityType}>
              <SelectTrigger id="entityType" className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ENTITY_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="entityId">엔터티 ID</Label>
            <Input
              id="entityId"
              className="w-96"
              placeholder="UUID"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
            />
          </div>
          <Button type="submit">조회</Button>
        </form>

        {!query ? (
          <EmptyState text="조회 조건을 입력하세요." />
        ) : (
          <DataState state={state} onRetry={state.reload} empty={{ text: '변경 이력이 없습니다.' }}>
            {(data) => (
              <>
                <DataTable<EntityHistoryResponse, unknown>
                  columns={columns}
                  data={data.content}
                  paginated={false}
                  emptyText="변경 이력이 없습니다."
                />
                <PaginationBar page={data} onChange={setPage} />
              </>
            )}
          </DataState>
        )}
      </div>
    </>
  );
}

function buildColumns(): ColumnDef<EntityHistoryResponse, unknown>[] {
  return [
    {
      accessorKey: 'field',
      header: ({ column }) => <SortableHeader column={column}>필드</SortableHeader>,
      cell: ({ row }) => <span className="font-mono text-xs">{row.original.field}</span>,
    },
    {
      accessorKey: 'fromValue',
      header: '이전',
      cell: ({ row }) => (
        <span className="block max-w-xs truncate">{row.original.fromValue ?? '-'}</span>
      ),
    },
    {
      accessorKey: 'toValue',
      header: '이후',
      cell: ({ row }) => (
        <span className="block max-w-xs truncate">{row.original.toValue ?? '-'}</span>
      ),
    },
    {
      id: 'actor',
      accessorFn: (h) => h.actorName ?? h.actor,
      header: ({ column }) => <SortableHeader column={column}>행위자</SortableHeader>,
    },
    {
      accessorKey: 'changedAt',
      header: ({ column }) => <SortableHeader column={column}>변경 시각</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum">{formatDateTime(row.original.changedAt)}</span>
      ),
    },
  ];
}
