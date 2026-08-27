import { useState, type ReactNode } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type Column,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { Pagination } from '@/components/ui/pagination';
import { SearchInput } from '@/components/ui/search-input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

/**
 * shadcn 데이터 표(TanStack Table). 정렬·거르기·쪽 넘김을 표가 맡는다.
 * 서버가 쪽을 나누는 화면은 paginated={false} 로 두고 바깥 PaginationBar 를 쓴다.
 */
export function DataTable<TData, TValue>({
  columns,
  data,
  filterColumn,
  filterPlaceholder = '표에서 찾기',
  pageSize = 20,
  paginated = true,
  emptyText = '내용이 없습니다.',
  onRowClick,
  className,
}: {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  filterColumn?: string;
  filterPlaceholder?: string;
  pageSize?: number;
  paginated?: boolean;
  emptyText?: string;
  onRowClick?: (row: TData) => void;
  className?: string;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    ...(paginated
      ? {
          getPaginationRowModel: getPaginationRowModel(),
          initialState: { pagination: { pageSize } },
        }
      : {}),
  });

  const rows = table.getRowModel().rows;

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {filterColumn && (
        <SearchInput
          value={(table.getColumn(filterColumn)?.getFilterValue() as string) ?? ''}
          onValueChange={(next) => table.getColumn(filterColumn)?.setFilterValue(next)}
          placeholder={filterPlaceholder}
          aria-label={filterPlaceholder}
          className="max-w-xs"
        />
      )}

      <div className="border-border bg-card overflow-hidden rounded-md border">
        <Table>
          <TableHeader className="bg-muted/60">
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((header) => (
                  <TableHead key={header.id} className="px-3">
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>

          <TableBody>
            {rows.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell
                  colSpan={columns.length}
                  className="text-muted-foreground text-sm py-10 text-center"
                >
                  {emptyText}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow
                  key={row.id}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onRowClick(row.original);
                          }
                        }
                      : undefined
                  }
                  className={onRowClick ? 'cursor-pointer' : undefined}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className="px-3 py-2.5">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {paginated && table.getPageCount() > 1 && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-muted-foreground text-sm tnum">
            {table.getState().pagination.pageIndex + 1} / {table.getPageCount()} 쪽 · 전체{' '}
            {table.getFilteredRowModel().rows.length}건
          </p>
          <Pagination
            page={table.getState().pagination.pageIndex}
            totalPages={table.getPageCount()}
            onChange={(p) => table.setPageIndex(p)}
          />
        </div>
      )}
    </div>
  );
}

/** 누르면 정렬되는 머리글. shadcn 데이터 표의 기본 짜임. */
export function SortableHeader<TData, TValue>({
  column,
  children,
}: {
  column: Column<TData, TValue>;
  children: ReactNode;
}) {
  const sorted = column.getIsSorted();
  const Icon = sorted === 'asc' ? ArrowUp : sorted === 'desc' ? ArrowDown : ChevronsUpDown;

  return (
    <button
      type="button"
      onClick={() => column.toggleSorting(sorted === 'asc')}
      className="text-foreground hover:text-primary -mx-1 flex items-center gap-1 rounded-sm px-1 font-medium transition-colors"
    >
      {children}
      <Icon className={cn('size-3.5', sorted ? 'text-primary' : 'text-muted-foreground')} />
    </button>
  );
}
