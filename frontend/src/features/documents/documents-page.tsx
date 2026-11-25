import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Upload } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { SearchInput } from '@/components/ui/search-input';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { PaginationBar } from '@/components/common/pagination-bar';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatBytes, formatDateTime } from '@/lib/format';
import { badgeVariantFor, label } from '@/lib/labels';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import { ALLOWED, rejectReason } from '@/features/documents/upload';
import { isProcessing, ProcessingBadge } from '@/features/documents/processing';
import type { DocumentUploadResponse, PageResponse } from '@/types/api';

const documentColumns = (projectId: string): ColumnDef<DocumentUploadResponse, unknown>[] => [
  {
    accessorKey: 'fileName',
    header: ({ column }) => <SortableHeader column={column}>파일명</SortableHeader>,
    cell: ({ row }) => (
      <Link
        to={`/p/${projectId}/documents/${row.original.id}`}
        className="block max-w-xs truncate underline-offset-2 hover:underline"
        title={row.original.fileName}
      >
        {row.original.fileName}
      </Link>
    ),
  },
  {
    accessorKey: 'fileSize',
    header: ({ column }) => <SortableHeader column={column}>크기</SortableHeader>,
    cell: ({ row }) => <span className="tnum">{formatBytes(row.original.fileSize)}</span>,
  },
  {
    accessorKey: 'status',
    header: '상태',
    cell: ({ row }) => (
      <>
        {row.original.processingState === 'DONE' ? (
          <Badge variant={badgeVariantFor(row.original.status)}>{label(row.original.status)}</Badge>
        ) : (
          <ProcessingBadge state={row.original.processingState} />
        )}
        {row.original.processingError && (
          <p className="text-destructive text-xs font-semibold tracking-wide mt-1">
            {row.original.processingError}
          </p>
        )}
        {!row.original.processingError && row.original.error && (
          <p className="text-destructive text-xs font-semibold tracking-wide mt-1">
            {row.original.error}
          </p>
        )}
      </>
    ),
  },
  {
    accessorKey: 'uploadedAt',
    header: ({ column }) => <SortableHeader column={column}>업로드</SortableHeader>,
    cell: ({ row }) => (
      <span className="text-muted-foreground tnum">{formatDateTime(row.original.uploadedAt)}</span>
    ),
  },
  {
    id: 'actions',
    header: '',
    cell: ({ row }) => (
      <div className="flex justify-end gap-2">
        <Button asChild size="sm" variant="ghost">
          <Link to={`/p/${projectId}/documents/${row.original.id}`}>상세</Link>
        </Button>
      </div>
    ),
  },
];

export function DocumentsPage(): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [page, setPage] = useState(0);
  const [progress, setProgress] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  // 글자마다 부르지 않게 잠깐 멈췄을 때 검색한다
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQ(search.trim());
      setPage(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // 자료 화면은 산출물과 무관한 일반 자료만 본다(11-19). 산출물은 산출물 화면에서 다룬다
  const state = useAsync<PageResponse<DocumentUploadResponse>>(
    () =>
      api.get<PageResponse<DocumentUploadResponse>>(
        `/projects/${project.id}/documents${toQueryString({ page, size: 20, general: true, q: q || undefined })}`,
      ),
    [project.id, page, q],
  );
  const { data, reload } = state;

  // 접수됨·처리 중인 문서가 있으면 끝날 때까지 다시 부른다. 처리는 뒤에서 한다(GH-121)
  const hasPending = (data?.content ?? []).some((d) => isProcessing(d.processingState));
  useEffect(() => {
    if (!hasPending) return;
    const timer = window.setInterval(reload, 2000);
    return () => window.clearInterval(timer);
  }, [hasPending, reload]);

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (inputRef.current) inputRef.current.value = '';
    if (!file) return;
    const reason = rejectReason(file);
    if (reason) {
      toast({ title: reason, variant: 'error' });
      return;
    }
    const form = new FormData();
    form.append('file', file);
    setProgress(0);
    try {
      await api.upload<DocumentUploadResponse>(`/projects/${project.id}/documents`, form, (r) =>
        setProgress(Math.round(r * 100)),
      );
      toast({
        title: '접수했습니다. 문서를 읽고 색인하는 동안 다른 화면을 써도 됩니다.',
        variant: 'success',
      });
      reload();
    } catch (err) {
      toast({
        title: '업로드에 실패했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setProgress(null);
    }
  };

  return (
    <>
      <PageHeader
        guide="deliverables#documents"
        title="자료"
        actions={
          <>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              aria-label="자료 파일"
              accept={ALLOWED.join(',')}
              onChange={upload}
            />
            <Button
              size="sm"
              onClick={() => inputRef.current?.click()}
              disabled={progress !== null}
            >
              <Upload />
              자료 업로드
            </Button>
          </>
        }
      />
      {progress !== null && (
        <div className="pb-4">
          <Progress value={progress} />
        </div>
      )}
      <SearchInput
        value={search}
        onValueChange={setSearch}
        placeholder="파일명 검색"
        aria-label="파일명 검색"
        className="mb-3 max-w-xs"
      />
      <DataState
        state={state}
        onRetry={reload}
        empty={{ text: q ? '찾는 자료가 없습니다.' : '올린 자료가 없습니다.' }}
      >
        {(pageData) => (
          <>
            <DataTable<DocumentUploadResponse, unknown>
              columns={documentColumns(project.id)}
              data={pageData.content}
              paginated={false}
              emptyText={q ? '찾는 자료가 없습니다.' : '올린 자료가 없습니다.'}
            />
            <PaginationBar page={pageData} onChange={setPage} />
          </>
        )}
      </DataState>
    </>
  );
}
