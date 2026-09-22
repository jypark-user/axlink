import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Markdown } from '@/components/ui/markdown';
import { Progress } from '@/components/ui/progress';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
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
import type { DocumentTextResponse, DocumentUploadResponse, PageResponse } from '@/types/api';

const documentColumns = (
  projectId: string,
  onShowText: (doc: DocumentUploadResponse) => void,
): ColumnDef<DocumentUploadResponse, unknown>[] => [
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
    cell: ({ row }) => (
      <div className="flex justify-end gap-2">
        {/* 읽기가 끝난 문서만. 글자 수가 있으면 추출본이 있다는 뜻이다 */}
        {row.original.extractedCharCount !== null && (
          <Button size="sm" variant="ghost" onClick={() => onShowText(row.original)}>
            추출 결과
          </Button>
        )}
        {row.original.draftAvailable && (
          <Button asChild size="sm" variant="outline">
            <Link to={`/p/${projectId}/documents/${row.original.id}/draft`}>초안 확인</Link>
          </Button>
        )}
      </div>
    ),
  },
];

/** 문서에서 뽑은 글을 그대로 보여 준다. 표가 행·열로 남았는지 여기서 확인한다(SWFR.CON.007). */
function TextSheet({
  doc,
  onClose,
}: {
  doc: DocumentUploadResponse | null;
  onClose: () => void;
}): ReactNode {
  const docId = doc?.id ?? null;
  const state = useAsync<DocumentTextResponse | null>(
    () => (docId ? api.get<DocumentTextResponse>(`/documents/${docId}/text`) : Promise.resolve(null)),
    [docId],
  );
  return (
    <Sheet open={doc !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="flex w-full flex-col gap-4 overflow-y-auto sm:max-w-2xl">
        {doc && (
          <SheetHeader>
            <SheetTitle className="text-base">{doc.fileName}</SheetTitle>
            {state.data && (
              <p className="text-muted-foreground text-sm tnum">
                {state.data.charCount.toLocaleString('ko-KR')}자
                {state.data.pageCount !== null && ` · ${state.data.pageCount}쪽`}
              </p>
            )}
          </SheetHeader>
        )}
        <DataState state={state} onRetry={state.reload} empty={{ text: '추출된 글이 없습니다.' }}>
          {(text) =>
            text && text.text.trim() ? (
              <Markdown className="text-sm leading-6">{text.text}</Markdown>
            ) : (
              <p className="text-muted-foreground text-sm">추출된 글이 없습니다.</p>
            )
          }
        </DataState>
      </SheetContent>
    </Sheet>
  );
}

// 추출까지가 지금의 종착점이다. 정형화(STRUCTURED)가 붙기 전까지 EXTRACTED 를
// 진행 중으로 보면 목록이 2초마다 영원히 다시 부른다.
const PENDING: string[] = ['UPLOADED'];

export function DocumentsPage(): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [page, setPage] = useState(0);
  const [progress, setProgress] = useState<number | null>(null);
  const [shown, setShown] = useState<DocumentUploadResponse | null>(null);

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
        description="산출물 문서를 올리는 자리입니다. 올린 문서는 AI 가 읽어 색인하고 산출물 유형과 요구사항 초안을 뽑습니다. 파일 이름이 WBS 산출물 열과 같으면 제출로 잡힙니다."
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
              columns={documentColumns(project.id, setShown)}
              data={pageData.content}
              paginated={false}
              emptyText="업로드된 문서가 없습니다."
            />
            <PaginationBar page={pageData} onChange={setPage} />
          </>
        )}
      </DataState>
      <TextSheet doc={shown} onClose={() => setShown(null)} />
    </>
  );
}
