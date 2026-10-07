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
        {row.original.draftAvailable && (
          <Button asChild size="sm" variant="outline">
            <Link to={`/p/${projectId}/documents/${row.original.id}/draft`}>초안 확인</Link>
          </Button>
        )}
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

  const state = useAsync<PageResponse<DocumentUploadResponse>>(
    () =>
      api.get<PageResponse<DocumentUploadResponse>>(
        `/projects/${project.id}/documents${toQueryString({ page, size: 20 })}`,
      ),
    [project.id, page],
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
        title="문서"
        description="산출물 문서를 올리는 자리입니다. 올린 문서는 AI 가 읽어 색인하고 산출물 유형과 요구사항 초안을 뽑습니다. PDF · DOCX · XLSX · PPTX · HWP · HWPX · MD · TXT 를 받고, 같은 파일을 다시 올리면 다시 읽습니다. 특정 WBS 항목의 산출물로 올리려면 산출물 화면의 올리기를 쓰십시오."
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
