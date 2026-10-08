import { useCallback, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { ServerLink } from '@/components/common/server-link';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDate, formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import { ALLOWED, rejectReason } from '@/features/documents/upload';
import { useAuth } from '@/features/auth/auth-context';
import { label } from '@/lib/labels';
import type {
  DeliverableStatus,
  DocumentUploadResponse,
  WbsDeliverableItem,
  WbsDeliverablesResponse,
  WorkProductChecklistResponse,
  WorkProductResponse,
} from '@/types/api';

/**
 * 산출물 화면. 본체는 WBS 가 정한 산출물 목록이다(ARC-016). 항목마다 제출·미제출·지연과
 * 근거, 붙은 문서, 29110 유형 태그가 한 줄로 보이고, 미제출 항목 옆에서 바로 올린다.
 * 22종 체크리스트는 인도 점검용으로 아래에 접어 둔다.
 */

type Filter = 'ALL' | 'OPEN' | 'SUBMITTED';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'ALL', label: '전체' },
  { key: 'OPEN', label: '미제출 · 지연' },
  { key: 'SUBMITTED', label: '제출' },
];

const STATUS_LABEL: Record<DeliverableStatus, string> = {
  NONE: '해당 없음',
  SUBMITTED: '제출',
  MISSING: '미제출',
  OVERDUE: '지연',
};

const STATUS_TONE: Record<DeliverableStatus, string> = {
  NONE: 'text-muted-foreground',
  SUBMITTED: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  MISSING: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  OVERDUE: 'bg-destructive/15 text-destructive',
};

const RULE_LABEL: Record<string, string> = {
  LINKED_DOC: '항목에 올린 문서',
  REPO_PATH: '저장소 파일',
  FILE_NAME: '같은 이름의 문서',
  PRODUCT_TYPE: '같은 유형의 산출물',
};

const inFilter = (item: WbsDeliverableItem, filter: Filter): boolean => {
  if (filter === 'ALL') return item.status !== 'NONE';
  if (filter === 'OPEN') return item.status === 'MISSING' || item.status === 'OVERDUE';
  return item.status === 'SUBMITTED';
};

export function DeliverablesPage(): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const [filter, setFilter] = useState<Filter>('ALL');
  const [showChecklist, setShowChecklist] = useState(false);
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const targetRef = useRef<string | null>(null);

  const state = useAsync<WbsDeliverablesResponse>(
    () => api.get<WbsDeliverablesResponse>(`/projects/${project.id}/wbs/deliverables`),
    [project.id],
  );
  const { reload } = state;

  const pickFile = (wbsId: string) => {
    targetRef.current = wbsId;
    inputRef.current?.click();
  };

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const wbsId = targetRef.current;
    if (inputRef.current) inputRef.current.value = '';
    if (!file || !wbsId) return;
    const reason = rejectReason(file);
    if (reason) {
      toast({ title: reason, variant: 'error' });
      return;
    }
    const form = new FormData();
    form.append('file', file);
    form.append('wbsId', wbsId);
    setUploadingFor(wbsId);
    try {
      await api.upload<DocumentUploadResponse>(`/projects/${project.id}/documents`, form);
      toast({
        title: `${wbsId} 항목의 산출물로 접수했습니다. 읽기·색인은 뒤에서 합니다.`,
        variant: 'success',
      });
      reload();
    } catch (err) {
      toast({
        title: '올리지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setUploadingFor(null);
    }
  };

  const columns = useMemo(
    () => buildColumns(project.id, pickFile, uploadingFor),
    [project.id, uploadingFor],
  );

  return (
    <>
      <PageHeader
        title="산출물"
        description="WBS 가 정한 산출물이 올라왔는지 봅니다. 저장소에 있거나 여기서 올린 문서가 근거입니다."
      />
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        aria-label="산출물 파일"
        accept={ALLOWED.join(',')}
        onChange={upload}
      />
      <DataState
        state={state}
        onRetry={reload}
        empty={{ text: 'WBS 가 없어 산출물 목록이 없습니다.' }}
      >
        {(data) => {
          const rows = data.items.filter((i) => inFilter(i, filter));
          const s = data.summary;
          const expected = s.submitted + s.missing + s.overdue;
          return (
            <>
              <p className="text-muted-foreground mb-3 text-sm">
                산출물 <span className="tnum text-foreground font-medium">{s.submitted}</span>/
                {expected}개 제출
                {s.overdue > 0 && (
                  <>
                    {' '}
                    · 지연 <span className="tnum text-destructive font-medium">{s.overdue}</span>개
                  </>
                )}{' '}
                · 기준일 {formatDate(data.baseDate)}
              </p>
              <Tabs value={filter} onValueChange={(next) => setFilter(next as Filter)}>
                <TabsList>
                  {FILTERS.map((tab) => (
                    <TabsTrigger key={tab.key} value={tab.key}>
                      {tab.label}
                      <span className="text-muted-foreground text-xs font-semibold tracking-wide tnum ml-1.5">
                        {data.items.filter((i) => inFilter(i, tab.key)).length}
                      </span>
                    </TabsTrigger>
                  ))}
                </TabsList>
                <DataTable<WbsDeliverableItem, unknown>
                  columns={columns}
                  data={rows}
                  filterColumn="name"
                  filterPlaceholder="작업이나 산출물 이름으로 찾기"
                  pageSize={50}
                  emptyText="해당하는 산출물이 없습니다."
                  className="mt-4"
                />
              </Tabs>

              <div className="mt-8">
                <Button variant="ghost" size="sm" onClick={() => setShowChecklist((v) => !v)}>
                  {showChecklist
                    ? '인도 점검표 접기'
                    : '인도 점검표 보기 (ISO/IEC 29110 산출물 22종)'}
                </Button>
                {showChecklist && <Checklist projectId={project.id} />}
              </div>
            </>
          );
        }}
      </DataState>
    </>
  );
}

function buildColumns(
  projectId: string,
  onUpload: (wbsId: string) => void,
  uploadingFor: string | null,
): ColumnDef<WbsDeliverableItem, unknown>[] {
  return [
    {
      accessorKey: 'wbsId',
      header: '번호',
      cell: ({ row }) => (
        <span className="tnum text-muted-foreground font-mono text-sm">{row.original.wbsId}</span>
      ),
    },
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column}>작업</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-[14rem] truncate text-sm" title={row.original.name}>
          {row.original.name}
        </span>
      ),
    },
    {
      accessorKey: 'deliverable',
      // WBS 산출물 열에 적힌 이름이다. 실제 파일이 아직 없을 수 있어 "정한" 을 붙인다.
      header: () => (
        <span title="WBS 산출물 열에 적힌 이름. 실제 파일과 다를 수 있다">WBS 가 정한 산출물</span>
      ),
      cell: ({ row }) => (
        <span
          className={cn(
            'block max-w-[18rem] truncate text-sm',
            row.original.status === 'SUBMITTED'
              ? 'text-muted-foreground'
              : 'text-muted-foreground/70 italic',
          )}
          title={`WBS 에 적힌 이름: ${row.original.deliverable ?? ''}`}
        >
          {row.original.deliverable ?? '-'}
        </span>
      ),
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <SortableHeader column={column}>판정</SortableHeader>,
      cell: ({ row }) => {
        const item = row.original;
        const pill = (
          <span
            className={cn(
              'inline-block rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
              STATUS_TONE[item.status],
            )}
          >
            {STATUS_LABEL[item.status]}
          </span>
        );
        const why = item.rule ? `${RULE_LABEL[item.rule] ?? item.rule}: ${item.ref ?? ''}` : null;
        // 근거가 올린 문서면 자료 상세로, 저장소 파일이면 원천(GitHub)으로 간다
        const docBacked = item.rule === 'LINKED_DOC' || item.rule === 'FILE_NAME';
        const detailDoc = docBacked ? item.documents[0] : undefined;
        return (
          <span className="flex flex-col gap-0.5">
            {detailDoc ? (
              <Link to={`/p/${projectId}/documents/${detailDoc.id}`} className="w-fit">
                {pill}
              </Link>
            ) : item.url ? (
              <ServerLink
                url={item.url}
                filename={item.deliverable ?? 'deliverable'}
                className="w-fit"
                title="원천 저장소에서 보기"
              >
                {pill}
              </ServerLink>
            ) : (
              <span className="w-fit">{pill}</span>
            )}
            {why && (
              <span className="text-muted-foreground max-w-[16rem] truncate text-xs" title={why}>
                {why}
              </span>
            )}
          </span>
        );
      },
    },
    {
      id: 'documents',
      header: '올린 문서',
      cell: ({ row }) => {
        const docs = row.original.documents;
        if (docs.length === 0) return <span className="text-muted-foreground text-sm">-</span>;
        return (
          <span className="flex flex-col gap-0.5">
            {docs.map((d) => (
              <Link
                key={d.id}
                to={`/p/${projectId}/documents/${d.id}`}
                className="max-w-[14rem] truncate text-sm underline-offset-2 hover:underline"
                title={`${d.fileName} · ${formatDateTime(d.uploadedAt)}`}
              >
                {d.fileName}
              </Link>
            ))}
          </span>
        );
      },
    },
    {
      accessorKey: 'productType',
      header: '유형',
      cell: ({ row }) =>
        row.original.productType ? (
          <span className="text-muted-foreground font-mono text-xs">
            {row.original.productType}
          </span>
        ) : (
          <span className="text-muted-foreground text-sm">-</span>
        ),
    },
    {
      accessorKey: 'endDate',
      header: ({ column }) => <SortableHeader column={column}>기한</SortableHeader>,
      cell: ({ row }) => (
        <span className="text-muted-foreground tnum text-sm">
          {row.original.endDate ? formatDate(row.original.endDate) : '-'}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        const item = row.original;
        if (item.status === 'NONE') return null;
        const busy = uploadingFor === item.wbsId;
        return (
          <div className="flex justify-end">
            <Button
              size="sm"
              variant={item.status === 'SUBMITTED' ? 'ghost' : 'outline'}
              disabled={busy}
              onClick={() => onUpload(item.wbsId)}
            >
              {busy ? '올리는 중…' : item.status === 'SUBMITTED' ? '새 버전 올리기' : '올리기'}
            </Button>
          </div>
        );
      },
    },
  ];
}

/** 인도 점검표. 22종 분류로 무엇이 채워졌는지 본다. 사업의 산출물 목록은 위 WBS 표다. */
function Checklist({ projectId }: { projectId: string }): ReactNode {
  const { me } = useAuth();
  const { toast } = useToast();
  // 승인·반려는 발주기관만. 서버도 역할과 사업 접근을 다시 본다
  const canApprove = me?.role === 'CLIENT' || me?.role === 'SUPER_ADMIN';
  const state = useAsync<WorkProductChecklistResponse>(
    () => api.get<WorkProductChecklistResponse>(`/projects/${projectId}/work-products`),
    [projectId],
  );
  const { reload } = state;
  const decide = useCallback(
    async (wp: WorkProductResponse, action: 'approve' | 'reject') => {
      const name = `${wp.title ?? wp.displayName} ${wp.version ?? ''}`.trim();
      let body: { reason: string } | undefined;
      if (action === 'reject') {
        const reason = window.prompt(`${name} 을(를) 반려하는 사유를 적어 주세요.`)?.trim();
        if (!reason) return;
        body = { reason };
      } else if (!window.confirm(`${name} 을(를) 승인합니다. 이 버전에만 붙습니다.`)) {
        return;
      }
      try {
        await api.post(`/projects/${projectId}/work-products/${wp.id}/${action}`, body ?? {});
        toast({
          title: action === 'approve' ? '승인했습니다.' : '반려했습니다.',
          variant: 'success',
        });
        reload();
      } catch (err) {
        toast({
          title: action === 'approve' ? '승인하지 못했습니다.' : '반려하지 못했습니다.',
          description: isApiError(err) ? err.message : undefined,
          variant: 'error',
        });
      }
    },
    [projectId, reload, toast],
  );
  const columns = useMemo<ColumnDef<WorkProductResponse, unknown>[]>(
    () => [
      {
        accessorKey: 'type',
        header: '유형',
        cell: ({ row }) => (
          <span className="text-muted-foreground font-mono text-xs">{row.original.type}</span>
        ),
      },
      {
        id: 'title',
        accessorFn: (wp) => wp.title ?? wp.displayName,
        header: '제목',
        cell: ({ row }) => (
          <span
            className={row.original.applicable ? 'text-foreground' : 'text-muted-foreground/60'}
          >
            {row.original.title ?? row.original.displayName}
          </span>
        ),
      },
      {
        accessorKey: 'status',
        header: '상태',
        cell: ({ row }) => {
          const wp = row.original;
          return (
            <div className="flex flex-col gap-0.5 text-sm">
              <span>{label(wp.status)}</span>
              {wp.status === 'APPROVED' && wp.approvedAt && (
                <span className="text-muted-foreground text-xs">
                  {wp.approvedBy ?? '-'} · {formatDate(wp.approvedAt)}
                </span>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: 'version',
        header: '버전',
        cell: ({ row }) => <span className="tnum text-sm">{row.original.version ?? '-'}</span>,
      },
      {
        id: 'activity',
        accessorFn: (wp) => wp.pmActivity ?? wp.siActivity ?? '',
        header: '활동',
        cell: ({ row }) => row.original.pmActivity ?? row.original.siActivity ?? '-',
      },
      ...(canApprove
        ? [
            {
              id: 'decide',
              header: '승인',
              cell: ({ row }: { row: { original: WorkProductResponse } }) => {
                const wp = row.original;
                if (wp.status !== 'SUBMITTED' && wp.status !== 'APPROVED') return null;
                return (
                  <div className="flex gap-1">
                    {wp.status === 'SUBMITTED' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void decide(wp, 'approve')}
                      >
                        승인
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => void decide(wp, 'reject')}>
                      반려
                    </Button>
                  </div>
                );
              },
            } satisfies ColumnDef<WorkProductResponse, unknown>,
          ]
        : []),
    ],
    [canApprove, decide],
  );
  return (
    <DataState state={state} onRetry={state.reload}>
      {(data) => (
        <DataTable<WorkProductResponse, unknown>
          columns={columns}
          data={data.items}
          paginated={false}
          emptyText="항목이 없습니다."
          className="mt-3"
        />
      )}
    </DataState>
  );
}
