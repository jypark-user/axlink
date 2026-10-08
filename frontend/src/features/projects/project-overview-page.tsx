import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Download, FileText, Pencil, Upload, X } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { DataState } from '@/components/common/data-state';
import { RequirementStatusBadge } from '@/components/common/requirement-status';
import { isProcessing } from '@/features/documents/processing';
import { Tile } from '@/components/ui/page';
import { Window } from '@/components/ui/window';
import { RESOURCE_DOCK_ID } from '@/components/layout/app-shell';
import { useProjectContext } from '@/components/layout/project-shell';
import { ResourceSheet } from '@/features/ax-query/resource-sheet';
import { AssignmentsPage } from '@/features/assignments/assignments-page';
import { useAuth } from '@/features/auth/auth-context';
import { useToast } from '@/components/common/toaster';
import { joinChunks, mergeChunks } from '@/features/documents/chunks';
import { tidyMarkdown } from '@/features/documents/tidy-markdown';
import { ALLOWED, rejectReason } from '@/features/documents/upload';
import { ProjectEditDialog } from '@/features/projects/project-edit-dialog';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatBytes, formatDateTime, formatPeriod } from '@/lib/format';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import { badgeVariantFor, label } from '@/lib/labels';
import { Markdown } from '@/components/ui/markdown';
import type {
  DocumentChunkResponse,
  DocumentStatus,
  DocumentUploadResponse,
  DraftRequirement,
  PageResponse,
  RequirementResponse,
  StructuringDraftResponse,
} from '@/types/api';

/** 원문 열람 자리. 질문 화면의 자료 칸과 같은 오른쪽 사이드바를 쓴다 — 요약을 옆에 두고 읽는다. */
function RawDocumentPanel({
  title,
  chunks,
  total,
  loading,
  onClose,
  onMore,
}: {
  title: string;
  chunks: DocumentChunkResponse[];
  total: number;
  loading: boolean;
  onClose: () => void;
  onMore: () => void;
}): ReactNode {
  const [dock, setDock] = useState<HTMLElement | null>(null);
  useEffect(() => setDock(document.getElementById(RESOURCE_DOCK_ID)), []);

  /** 조각은 쪽 넓이에서 끊긴 그대로다 — 이어 붙인 뒤 한 번에 편다. */
  const text = useMemo(() => tidyMarkdown(joinChunks(chunks)), [chunks]);

  /** 끝까지 내려가면 다음 쪽을 알아서 잇는다 — 누를 것은 없다. */
  const endRef = useRef<HTMLDivElement>(null);
  const more = useRef(onMore);
  more.current = onMore;
  useEffect(() => {
    const el = endRef.current;
    if (!el || loading || chunks.length === 0 || chunks.length >= total) return;
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) more.current();
    });
    io.observe(el);
    return () => io.disconnect();
  }, [chunks.length, total, loading]);

  if (!dock) return null;

  return createPortal(
    <ResourceSheet label="원문">
      <div className="flex h-full flex-col">
        <div className="border-border flex items-center gap-2 border-b px-4 py-3">
          <FileText className="text-muted-foreground size-4 shrink-0" />
          <span className="text-sm min-w-0 flex-1 truncate font-medium">{title}</span>
          <Button variant="ghost" size="icon" className="size-7" onClick={onClose}>
            <X className="size-4" />
            <span className="sr-only">원문 닫기</span>
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {chunks.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              {loading ? '본문을 읽는 중입니다…' : '이 자료에서 읽어 낸 본문이 없습니다.'}
            </p>
          ) : (
            <>
              <Markdown>{text}</Markdown>
              <div ref={endRef} className="h-8" />
              {loading && (
                <p className="text-muted-foreground text-sm text-center">이어 읽는 중…</p>
              )}
            </>
          )}
        </div>
      </div>
    </ResourceSheet>,
    dock,
  );
}

export function ProjectOverviewPage(): ReactNode {
  const { project, replaceProject } = useProjectContext();
  const { me } = useAuth();
  const [editOpen, setEditOpen] = useState(false);
  const canEdit = me?.role === 'CLIENT';
  const canUpload = canEdit || me?.role === 'SUPER_ADMIN';

  return (
    <div className="@container">
      <div className="grid grid-cols-1 items-start gap-3 @3xl:grid-cols-12">
        <Tile span={12}>
          <Window
            title="기본 정보"
            hint="사업을 등록할 때 입력한 내용입니다."
            action={
              canEdit ? (
                <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                  <Pencil className="size-4" />
                  수정
                </Button>
              ) : null
            }
          >
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 @2xl:grid-cols-2">
              <Row term="사업명" desc={project.name} />
              <Row term="사업 기간" desc={formatPeriod(project.startDate, project.endDate)} />
              <Row term="발주사" desc={project.clientOrgName} />
              <Row term="용역사" desc={project.contractorName} />
              <Row term="현재 SI 단계" desc={label(project.currentSiPhase)} />
              <Row term="최근 수정" desc={formatDateTime(project.updatedAt)} />
            </dl>

            <p className="text-foreground text-sm mt-5 whitespace-pre-line">
              {project.description || '설명이 없습니다.'}
            </p>
          </Window>
        </Tile>

        {canEdit && (
          <Tile span={12}>
            <Window title="용역사" hint="이 사업에 참여한 용역사 계정입니다.">
              <AssignmentsPage embedded />
            </Window>
          </Tile>
        )}

        <Tile span={12}>
          <ProjectDetailSummary projectId={project.id} canUpload={canUpload} />
        </Tile>

        <Tile span={12}>
          <ProjectRequirements projectId={project.id} />
        </Tile>
      </div>

      {canEdit && (
        <ProjectEditDialog
          project={project}
          open={editOpen}
          onOpenChange={setEditOpen}
          onSaved={replaceProject}
        />
      )}
    </div>
  );
}

/** 아직 읽는 중인 상태 — 하나라도 남아 있으면 목록을 다시 읽는다. */
const READING: DocumentStatus[] = ['UPLOADED'];
/**
 * 색인이 끝나 근거로 쓸 수 있는 상태.
 * 업로드 시점에 본문을 읽고 바로 색인하므로 EXTRACTED 부터 원문을 펼 수 있다.
 * STRUCTURED·CONFIRMED 는 정형화까지 끝난 상태로, 읽기에는 차이가 없다.
 */
const INDEXED: DocumentStatus[] = ['EXTRACTED', 'STRUCTURED', 'CONFIRMED'];
const POLL_MS = 3000;
/** 한 쪽에 담는 본문 조각 수 — 너무 많으면 읽기 버겁다. */
/** 본문은 읽는 화면이라 쪽을 넘기지 않고 이어 붙인다 — 한 번에 이만큼씩 더 가져온다. */
// 한 번에 읽어 오는 조각 수. 요구사항은 문서 한가운데 있어 너무 조금씩 받으면 한참 굴려야 나온다.
const CHUNK_STEP = 50;

/**
 * 사업 세부 내용. 사람이 채우는 칸이 아니라, 올린 자료에서 AI 가 정리해 주는 자리다.
 * 자료를 올리면 읽는 상태를 보여 주고, 색인이 끝나면 스스로 정리해 아래에 펼친다.
 */
function ProjectDetailSummary({
  projectId,
  canUpload,
}: {
  projectId: string;
  canUpload: boolean;
}): ReactNode {
  const { toast } = useToast();
  const [progress, setProgress] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  /** 펴 볼 자료와 그 안에서 보고 있는 쪽. */
  const [picked, setPicked] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const documents = useAsync<PageResponse<DocumentUploadResponse>>(
    () =>
      api.get<PageResponse<DocumentUploadResponse>>(
        `/projects/${projectId}/documents${toQueryString({ page: 0, size: 20 })}`,
      ),
    [projectId],
  );

  const files = documents.data?.content ?? [];
  // 처리는 뒤에서 한다(GH-121). 접수됨·처리 중인 자료가 있으면 따라간다
  const reading = files.some((d) => isProcessing(d.processingState) || READING.includes(d.status));
  const indexedCount = files.filter((d) => INDEXED.includes(d.status)).length;
  const { reload } = documents;

  // 읽는 중인 자료가 있으면 끝날 때까지 상태를 따라간다.
  useEffect(() => {
    if (!reading) return;
    const timer = window.setInterval(reload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [reading, reload]);

  // 이름을 누른 자료만 편다.
  const openId = picked;

  /** 원문은 파일 이름을 눌렀을 때 오른쪽 자리에 편다. */
  const [rawOpen, setRawOpen] = useState(false);
  /** 삭제 확인을 기다리는 자료. */
  const [removing, setRemoving] = useState<DocumentUploadResponse | null>(null);

  const body = useAsync<PageResponse<DocumentChunkResponse> | null>(
    () =>
      openId
        ? api.get<PageResponse<DocumentChunkResponse>>(
            `/documents/${openId}/chunks${toQueryString({ page, size: CHUNK_STEP })}`,
          )
        : Promise.resolve(null),
    [openId, page, indexedCount],
  );

  /** 지금까지 읽어 내린 본문. 다른 자료를 펴면 처음부터 다시 쌓는다. */
  const [shown, setShown] = useState<DocumentChunkResponse[]>([]);
  useEffect(() => setShown([]), [openId]);
  useEffect(() => {
    const got = body.data?.content;
    if (got) setShown((prev) => mergeChunks(prev, got));
  }, [body.data]);

  const total = body.data?.totalElements ?? 0;

  /** 올린 자료를 그대로 받아 둔다 — 색인한 글이 아니라 원본 파일이다. */
  const save = async (file: DocumentUploadResponse) => {
    try {
      await api.download(`/documents/${file.id}/content`, file.fileName);
    } catch (err) {
      toast({
        title: isApiError(err) ? err.message : '자료를 내려받지 못했습니다.',
        variant: 'error',
      });
    }
  };

  /** 여러 파일을 한 번에 받아 차례로 올린다 — 하나가 막혀도 나머지는 계속 간다. */
  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const list = [...(e.target.files ?? [])];
    if (fileRef.current) fileRef.current.value = '';
    if (list.length === 0) return;

    setProgress(0);
    let failed = 0;
    for (const [i, file] of list.entries()) {
      const reason = rejectReason(file);
      if (reason) {
        failed += 1;
        toast({ title: `${file.name}: ${reason}`, variant: 'error' });
        continue;
      }
      const form = new FormData();
      form.append('file', file);
      try {
        await api.upload<DocumentUploadResponse>(`/projects/${projectId}/documents`, form, (r) =>
          setProgress(Math.round(((i + r) / list.length) * 100)),
        );
      } catch (err) {
        failed += 1;
        toast({
          title: `${file.name} 업로드에 실패했습니다.`,
          description: isApiError(err) ? err.message : undefined,
          variant: 'error',
        });
      }
    }
    setProgress(null);
    if (failed < list.length) reload();
  };

  /** 자료를 지운다 — 색인된 내용도 함께 사라진다. */
  const remove = async (file: DocumentUploadResponse) => {
    setRemoving(null);
    try {
      await api.del<void>(`/documents/${file.id}`);
      if (picked === file.id) setPicked(null);
      setRawOpen(false);
      reload();
    } catch (err) {
      toast({
        title: '자료를 지우지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <Window
      title="사업 세부 내용"
      hint="올린 자료에서 AI 가 정리한 내용입니다."
      action={
        canUpload ? (
          <>
            <input
              ref={fileRef}
              type="file"
              multiple
              className="hidden"
              aria-label="관련자료 파일"
              accept={ALLOWED.join(',')}
              onChange={upload}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => fileRef.current?.click()}
              disabled={progress !== null}
            >
              <Upload className="size-4" />
              {progress === null ? '관련자료 업로드' : `올리는 중 ${progress}%`}
            </Button>
          </>
        ) : null
      }
    >
      {progress !== null && <Progress value={progress} className="mb-4 h-1.5" />}

      {files.length > 0 && (
        <ul className="flex flex-col gap-2">
          {files.map((file) => (
            <li
              key={file.id}
              className="border-border flex items-center gap-3 rounded-md border px-3 py-2"
            >
              <FileText className="text-muted-foreground size-4 shrink-0" />
              <span className="min-w-0 flex-1">
                {/* 파일 이름을 누르면 오른쪽에 원문이 펴진다. */}
                {INDEXED.includes(file.status) ? (
                  <button
                    type="button"
                    onClick={() => {
                      setPicked(file.id);
                      setPage(0);
                      setRawOpen(true);
                    }}
                    title={`${file.fileName} 원문 보기`}
                    className="hover:text-primary block max-w-full cursor-pointer truncate text-left text-sm font-medium underline underline-offset-2"
                  >
                    {file.fileName}
                  </button>
                ) : (
                  <span className="block truncate text-sm font-medium">{file.fileName}</span>
                )}
                <span className="text-muted-foreground text-xs font-semibold tracking-wide tnum">
                  {formatBytes(file.fileSize)} · {formatDateTime(file.uploadedAt)}
                </span>
              </span>
              {isProcessing(file.processingState) && (
                <span className="text-muted-foreground text-xs font-semibold tracking-wide shrink-0">
                  {file.processingState === 'QUEUED' ? '접수됨' : '읽는 중'}
                </span>
              )}
              {file.processingState === 'FAILED' && (
                <span
                  className="text-destructive text-xs font-semibold tracking-wide shrink-0"
                  title={file.processingError ?? undefined}
                >
                  처리 실패
                </span>
              )}
              <Button
                size="icon"
                variant="ghost"
                className="size-8 shrink-0"
                aria-label={`${file.fileName} 내려받기`}
                onClick={() => save(file)}
              >
                <Download className="size-4" />
              </Button>
              {canUpload && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="hover:text-destructive size-8 shrink-0"
                  aria-label={`${file.fileName} 삭제`}
                  onClick={() => setRemoving(file)}
                >
                  <X className="size-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {files.length === 0 && (
        <p className="text-muted-foreground text-sm">
          아직 올린 자료가 없습니다. 제안요청서·과업지시서 같은 관련자료를 올리면 이름을 눌러 원문을
          볼 수 있습니다.
        </p>
      )}

      {rawOpen && openId && (
        <RawDocumentPanel
          title={files.find((f) => f.id === openId)?.fileName ?? '원문'}
          chunks={shown}
          total={total}
          loading={body.loading}
          onClose={() => setRawOpen(false)}
          onMore={() => setPage((p) => p + 1)}
        />
      )}

      <AlertDialog open={removing !== null} onOpenChange={(open) => !open && setRemoving(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>‘{removing?.fileName}’ 을 삭제할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              색인된 내용과 함께 지워지고, 되돌릴 수 없습니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>남겨두기</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90 text-white"
              onClick={() => removing && remove(removing)}
            >
              삭제
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Window>
  );
}

const requirementColumns: ColumnDef<RequirementResponse, unknown>[] = [
  {
    accessorKey: 'code',
    header: ({ column }) => <SortableHeader column={column}>코드</SortableHeader>,
    cell: ({ row }) => (
      <span className="text-muted-foreground font-mono text-xs">{row.original.code}</span>
    ),
  },
  {
    accessorKey: 'title',
    header: ({ column }) => <SortableHeader column={column}>요구사항</SortableHeader>,
    cell: ({ row }) => (
      <span className="block max-w-xl truncate" title={row.original.title}>
        {row.original.title}
      </span>
    ),
  },
  {
    accessorKey: 'priority',
    header: ({ column }) => <SortableHeader column={column}>중요도</SortableHeader>,
    cell: ({ row }) => (
      <Badge variant={badgeVariantFor(row.original.priority)}>{label(row.original.priority)}</Badge>
    ),
  },
  {
    accessorKey: 'status',
    header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
    cell: ({ row }) => (
      <RequirementStatusBadge status={row.original.status} basis={row.original.statusBasis} />
    ),
  },
];

/** 올린 문서에서 뽑혀 확정된 요구사항. 초안 확인에서 확정한 것이 여기 쌓인다. */
/** 아직 등록 전인 요구사항 — 문서에서 읽어 온 그대로다. 상태 칸이 없다. */
const draftRequirementColumns: ColumnDef<DraftRequirement, unknown>[] = [
  {
    accessorKey: 'code',
    header: ({ column }) => <SortableHeader column={column}>코드</SortableHeader>,
    cell: ({ row }) => (
      <span className="text-muted-foreground font-mono text-xs">
        {row.original.code ?? `#${row.original.index + 1}`}
      </span>
    ),
  },
  {
    accessorKey: 'title',
    header: ({ column }) => <SortableHeader column={column}>요구사항</SortableHeader>,
    cell: ({ row }) => (
      <span className="block max-w-xl truncate" title={row.original.body ?? row.original.title}>
        {row.original.title}
      </span>
    ),
  },
  {
    accessorKey: 'priority',
    header: ({ column }) => <SortableHeader column={column}>중요도</SortableHeader>,
    cell: ({ row }) => (
      <Badge variant={badgeVariantFor(row.original.priority)}>{label(row.original.priority)}</Badge>
    ),
  },
];

function ProjectRequirements({ projectId }: { projectId: string }): ReactNode {
  const state = useAsync<PageResponse<RequirementResponse>>(
    () =>
      api.get<PageResponse<RequirementResponse>>(
        `/projects/${projectId}/requirements${toQueryString({ page: 0, size: 100 })}`,
      ),
    [projectId],
  );

  const rows = state.data?.content ?? [];

  /**
   * 등록된 요구사항이 없으면 문서 초안에서 읽어 온다.
   * 색인은 끝났지만 확정 전이라 표가 비어 있는 동안에도, 문서에 적힌 요구사항은 보여야 한다.
   */
  const drafted = useAsync<DraftRequirement[]>(async () => {
    if (state.loading || rows.length > 0) return [];
    const docs = await api.get<PageResponse<DocumentUploadResponse>>(
      `/projects/${projectId}/documents${toQueryString({ page: 0, size: 20 })}`,
    );
    const found: DraftRequirement[] = [];
    for (const doc of docs.content.filter((d) => d.draftAvailable)) {
      const draft = await api
        .get<StructuringDraftResponse>(`/documents/${doc.id}/draft`)
        .catch(() => null);
      if (draft) found.push(...draft.requirements);
    }
    return found;
  }, [projectId, state.loading, rows.length]);

  const fromDraft = drafted.data ?? [];

  return (
    <Window
      title="요구사항"
      hint={
        rows.length > 0
          ? `올린 문서에서 정리된 ${rows.length}건입니다.`
          : fromDraft.length > 0
            ? `올린 문서에서 읽어 온 ${fromDraft.length}건입니다. 아직 등록 전이라 추적에는 연결되지 않습니다.`
            : '올린 문서에서 요구사항을 뽑아내면 여기 쌓입니다.'
      }
      action={
        rows.length > 0 ? (
          <Button asChild variant="outline" size="sm">
            <Link to={`/p/${projectId}/traceability`}>추적 보기</Link>
          </Button>
        ) : null
      }
    >
      <DataState state={state} onRetry={state.reload}>
        {(page) =>
          page.content.length === 0 ? (
            fromDraft.length > 0 ? (
              <DataTable<DraftRequirement, unknown>
                columns={draftRequirementColumns}
                data={fromDraft}
                filterColumn="title"
                filterPlaceholder="요구사항으로 찾기"
                pageSize={10}
              />
            ) : (
              <p className="text-muted-foreground text-sm">
                {drafted.loading
                  ? '문서에서 읽어 오는 중입니다…'
                  : '아직 정리된 요구사항이 없습니다. 관련자료를 올리면 문서에서 뽑아 여기 쌓입니다.'}
              </p>
            )
          ) : (
            <DataTable<RequirementResponse, unknown>
              columns={requirementColumns}
              data={page.content}
              filterColumn="title"
              filterPlaceholder="요구사항으로 찾기"
              pageSize={10}
            />
          )
        }
      </DataState>
    </Window>
  );
}

function Row({ term, desc }: { term: string; desc: ReactNode }): ReactNode {
  return (
    <div className="flex min-w-0 items-baseline gap-3">
      <dt className="text-muted-foreground text-sm w-24 shrink-0">{term}</dt>
      <dd className="text-foreground text-sm min-w-0 truncate">{desc}</dd>
    </div>
  );
}
