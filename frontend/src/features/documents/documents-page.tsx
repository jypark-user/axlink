import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
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
import type { DocumentUploadResponse, PageResponse } from '@/types/api';

const documentColumns = (projectId: string): ColumnDef<DocumentUploadResponse, unknown>[] => [
  {
    accessorKey: 'fileName',
    header: ({ column }) => <SortableHeader column={column}>파일명</SortableHeader>,
    cell: ({ row }) => (
      <span className="block max-w-xs truncate" title={row.original.fileName}>
        {row.original.fileName}
      </span>
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
        <Badge variant={badgeVariantFor(row.original.status)}>{label(row.original.status)}</Badge>
        {row.original.error && (
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
    cell: ({ row }) =>
      row.original.draftAvailable ? (
        <div className="flex justify-end">
          <Button asChild size="sm" variant="outline">
            <Link to={`/p/${projectId}/documents/${row.original.id}/draft`}>초안 확인</Link>
          </Button>
        </div>
      ) : null,
  },
];

const PENDING: string[] = ['UPLOADED', 'EXTRACTED'];

export function DocumentsPage(): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [page, setPage] = useState(0);
  const [progress, setProgress] = useState<number | null>(null);

  const state = useAsync<PageResponse<DocumentUploadResponse>>(
    () =>
      api.get<PageResponse<DocumentUploadResponse>>(
        `/projects/${project.id}/documents${toQueryString({ page, size: 20 })}`,
      ),
    [project.id, page],
  );
  const { data, reload } = state;

  const hasPending = (data?.content ?? []).some((d) => PENDING.includes(d.status));
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
      toast({ title: '올렸습니다. 문서를 읽고 색인합니다.', variant: 'success' });
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
        title="문서"
        description="올린 문서는 AI 가 읽어 색인하고, 요구사항 초안을 뽑습니다."
        actions={
          <>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              aria-label="문서 파일"
              accept={ALLOWED.join(',')}
              onChange={upload}
            />
            <Button
              size="sm"
              onClick={() => inputRef.current?.click()}
              disabled={progress !== null}
            >
              문서 업로드
            </Button>
          </>
        }
      />
      {progress !== null && (
        <div className="pb-4">
          <Progress value={progress} />
        </div>
      )}
      <DataState state={state} onRetry={reload} empty={{ text: '업로드된 문서가 없습니다.' }}>
        {(pageData) => (
          <>
            <DataTable<DocumentUploadResponse, unknown>
              columns={documentColumns(project.id)}
              data={pageData.content}
              paginated={false}
              emptyText="업로드된 문서가 없습니다."
            />
            <PaginationBar page={pageData} onChange={setPage} />
          </>
        )}
      </DataState>
    </>
  );
}
