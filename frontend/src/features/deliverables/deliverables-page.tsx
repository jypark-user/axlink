import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ReactNode,
} from 'react';
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
import {
  DesignateDialog,
  DesignatedCell,
  DesignatedSheet,
  RedesignationPanel,
  UploadDialog,
  type DesignatedActions,
  type DesignationTarget,
} from './designated';
import { useTypeNames } from './use-type-names';
import { ReviewBadge, ReviewButton } from './review-button';
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
  DESIGNATED: '발주기관 지정 산출물',
};

const inFilter = (item: WbsDeliverableItem, filter: Filter): boolean => {
  // 산출물 열이 빈 작업(해당 없음)도 보인다. 발주기관이 거기에도 산출물을 지정할 수 있다
  if (filter === 'ALL') return true;
  if (filter === 'OPEN') return item.status === 'MISSING' || item.status === 'OVERDUE';
  return item.status === 'SUBMITTED';
};

export function DeliverablesPage(): ReactNode {
  const { project } = useProjectContext();
  const { toast } = useToast();
  const [filter, setFilter] = useState<Filter>('ALL');
  const [showChecklist, setShowChecklist] = useState(false);
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);
  const [designating, setDesignating] = useState<DesignationTarget | null>(null);
  const [openWbsId, setOpenWbsId] = useState<string | null>(null);
  // 양식이 있는 작업의 올리기 창
  const [uploadWbsId, setUploadWbsId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // 올릴 자리. 지정 산출물 항목을 골라 올리면 그 항목의 제출본이 된다(UC-033)
  const targetRef = useRef<{ wbsId: string; designatedId?: string } | null>(null);
  const { me } = useAuth();
  // 산출물 지정은 발주기관만. 관리자는 대신하지 않는다(DEC-05). 서버도 다시 본다
  const canDesignate = me?.role === 'CLIENT';
  const typeNames = useTypeNames(project.id);

  const state = useAsync<WbsDeliverablesResponse>(
    () => api.get<WbsDeliverablesResponse>(`/projects/${project.id}/wbs/deliverables`),
    [project.id],
  );
  const { reload } = state;
  // 올린 문서를 읽는 중이면 몇 초마다 다시 받아, 끝나는 대로 「제출」로 바뀐 것을 보인다
  const reading = (state.data?.items ?? []).some((i) =>
    (i.designated ?? []).some((d) => d.versions.some((v) => v.submit === 'PROCESSING')),
  );
  useEffect(() => {
    if (!reading) return;
    const timer = window.setInterval(reload, 4000);
    return () => window.clearInterval(timer);
  }, [reading, reload]);

  const pickFile = (wbsId: string, designatedId?: string) => {
    targetRef.current = { wbsId, designatedId };
    inputRef.current?.click();
  };

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const target = targetRef.current;
    if (inputRef.current) inputRef.current.value = '';
    if (!file || !target) return;
    const { wbsId, designatedId } = target;
    const reason = rejectReason(file);
    if (reason) {
      toast({ title: reason, variant: 'error' });
      return;
    }
    const form = new FormData();
    form.append('file', file);
    if (designatedId) form.append('designatedId', designatedId);
    else form.append('wbsId', wbsId);
    setUploadingFor(wbsId);
    try {
      await api.upload<DocumentUploadResponse>(`/projects/${project.id}/documents`, form);
      toast({
        title: designatedId
          ? `${wbsId} 작업의 산출물로 올렸습니다. 문서를 읽고 나면 제출로 바뀝니다.`
          : `${wbsId} 항목의 산출물로 접수했습니다. 읽기·색인은 뒤에서 합니다.`,
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

  const designatedActions: DesignatedActions = {
    projectId: project.id,
    canDesignate,
    typeNames,
    onUpload: pickFile,
    onEdit: setDesignating,
    onChanged: reload,
    onOpen: setOpenWbsId,
  };

  const columns = useMemo(
    () =>
      buildColumns(
        project.id,
        pickFile,
        setUploadWbsId,
        uploadingFor,
        designatedActions,
        typeNames,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [project.id, uploadingFor, canDesignate, typeNames, reload],
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
              <RedesignationPanel
                entries={data.redesignation ?? []}
                tasks={data.items}
                actions={designatedActions}
              />
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
                  filterPlaceholder="검색"
                  pageSize={50}
                  emptyText="해당하는 산출물이 없습니다."
                  className="mt-4"
                />
              </Tabs>

              <DesignatedSheet
                item={data.items.find((i) => i.wbsId === openWbsId) ?? null}
                actions={designatedActions}
                onClose={() => setOpenWbsId(null)}
              />
              <UploadDialog
                item={data.items.find((i) => i.wbsId === uploadWbsId) ?? null}
                actions={designatedActions}
                onClose={() => setUploadWbsId(null)}
              />

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
      {designating && (
        <DesignateDialog
          projectId={project.id}
          target={designating}
          typeNames={typeNames}
          onClose={() => setDesignating(null)}
          onDone={() => {
            setDesignating(null);
            reload();
          }}
        />
      )}
    </>
  );
}

function buildColumns(
  projectId: string,
  onUpload: (wbsId: string) => void,
  onOpenUpload: (wbsId: string) => void,
  uploadingFor: string | null,
  designatedActions: DesignatedActions,
  typeNames: Record<string, string>,
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
      // 작업명만 둔다(11-18 사용자 지시)
      id: 'name',
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column}>작업명</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-[17rem] truncate text-sm" title={row.original.name}>
          {row.original.name}
        </span>
      ),
    },
    {
      id: 'designated',
      // 발주기관이 정한 산출물 양식(UC-033). 있으면 판정이 WBS 산출물 열 대신 이것을 본다
      header: '산출물 양식',
      cell: ({ row }) => <DesignatedCell item={row.original} actions={designatedActions} />,
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
        // 근거가 올린 문서면 자료 상세로, 저장소 파일이면 그 저장소(GitHub)로 간다
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
                title="저장소에서 보기"
              >
                {pill}
              </ServerLink>
            ) : (
              <span className="w-fit">{pill}</span>
            )}
            {/* 제출본의 승인 상태(11-18). 제출과 승인은 다른 일이라 따로 보인다 */}
            <ReviewBadge item={item} />
            {why && (
              <span className="text-muted-foreground max-w-[11rem] truncate text-xs" title={why}>
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
        const [first, ...rest] = docs;
        return (
          <span className="flex max-w-[11rem] flex-col">
            <Link
              to={`/p/${projectId}/documents/${first.id}`}
              className="truncate text-sm underline-offset-2 hover:underline"
              title={docs.map((d) => `${d.fileName} · ${formatDateTime(d.uploadedAt)}`).join(', ')}
            >
              {first.fileName}
            </Link>
            {rest.length > 0 && (
              <span className="text-muted-foreground text-xs">외 {rest.length}건</span>
            )}
          </span>
        );
      },
    },
    {
      accessorKey: 'productType',
      // 붙은 문서의 29110 산출물 분류. 코드 대신 이름으로 보인다(인도 점검표와 같은 이름)
      header: () => <span title="붙은 문서의 ISO/IEC 29110 산출물 분류">문서 분류</span>,
      cell: ({ row }) =>
        row.original.productType ? (
          <span
            className="text-muted-foreground block max-w-[7rem] truncate text-xs"
            title={typeNames[row.original.productType] ?? row.original.productType}
          >
            {typeNames[row.original.productType] ?? row.original.productType}
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
        // 산출물 제출은 이 [올리기]로만 한다(11-18 사용자 지시). 양식이 있으면 양식을 골라 올리는
        // 창을 열고, 없으면 바로 파일을 고른다
        const hasForm = (item.designated ?? []).some((d) => !d.needsRedesignation);
        if (!hasForm && item.status === 'NONE') return null;
        const busy = uploadingFor === item.wbsId;
        return (
          <div className="flex items-center justify-end gap-2">
            {/* 올라온 제출본의 승인·반려(11-18). 양식 창이 아니라 여기서 한다 */}
            <ReviewButton
              projectId={projectId}
              item={item}
              canReview={designatedActions.canDesignate}
              onChanged={designatedActions.onChanged}
            />
            <Button
              size="sm"
              disabled={busy}
              onClick={() => (hasForm ? onOpenUpload(item.wbsId) : onUpload(item.wbsId))}
            >
              {busy ? '올리는 중…' : '올리기'}
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
  const canApprove = me?.role === 'CLIENT'; // 관리자는 대신하지 않는다(DEC-05)
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
        header: '분류',
        cell: ({ row }) => (
          <span className="text-muted-foreground text-xs" title={row.original.type}>
            {row.original.displayName}
          </span>
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
        cell: ({ row }) => {
          const wp = row.original;
          return (
            <div className="flex flex-col gap-0.5 text-sm">
              <span className="tnum">{wp.version ?? '-'}</span>
              {wp.previousVersions.length > 0 && (
                <details className="text-muted-foreground text-xs">
                  <summary className="cursor-pointer">
                    지난 버전 {wp.previousVersions.length}건
                  </summary>
                  <ul className="mt-1 flex flex-col gap-1">
                    {wp.previousVersions.map((h) => (
                      <li key={h.id}>
                        <span className="tnum">{h.version ?? '-'}</span> · {label(h.status)}
                        {h.decidedAt && (
                          <>
                            {' '}
                            · {h.decidedBy ?? '-'} · {formatDate(h.decidedAt)}
                          </>
                        )}
                        {h.rejectReason && <div>반려 사유: {h.rejectReason}</div>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          );
        },
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
