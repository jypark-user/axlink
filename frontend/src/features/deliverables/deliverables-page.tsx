import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDate } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import { ALLOWED, rejectReason } from '@/features/documents/upload';
import { useAuth } from '@/features/auth/auth-context';
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
import { ReviewButton } from './review-button';
import { Iso29110Button } from './iso29110-panel';
import { RepoPickDialog, UploadMenu, type UploadTarget } from './repo-upload';
import type {
  DeliverableStatus,
  DocumentUploadResponse,
  WbsDeliverableItem,
  WbsDeliverablesResponse,
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

const BAR_TONE: Record<DeliverableStatus, string> = {
  NONE: 'bg-muted-foreground',
  SUBMITTED: 'bg-emerald-500',
  MISSING: 'bg-amber-500',
  OVERDUE: 'bg-destructive',
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
  // 산출물로 고를 수 있는 저장소 파일(11-19). 없으면 올리기가 바로 파일을 고른다
  const repoFiles = useAsync<{ paths: string[] }>(
    () => api.get<{ paths: string[] }>(`/projects/${project.id}/repository-files`),
    [project.id],
  );
  const repoPaths = repoFiles.data?.paths ?? [];
  const [repoTarget, setRepoTarget] = useState<UploadTarget | null>(null);

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
        title: `${wbsId} 작업의 산출물로 제출했습니다.`,
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
    onUploadRepo: (wbsId, designatedId) => setRepoTarget({ wbsId, designatedId }),
    hasRepo: repoPaths.length > 0,
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
    [project.id, uploadingFor, canDesignate, typeNames, reload, repoPaths.length],
  );

  return (
    <>
      <PageHeader title="산출물" actions={<Iso29110Button projectId={project.id} />} />
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
                onUploadPlain={(wbsId) => pickFile(wbsId)}
              />
              <RepoPickDialog
                projectId={project.id}
                target={repoTarget}
                paths={repoPaths}
                onClose={() => setRepoTarget(null)}
                onDone={(wbsId) => {
                  toast({ title: `${wbsId} 작업의 산출물로 제출했습니다.`, variant: 'success' });
                  reload();
                }}
              />
            </>
          );
        }}
      </DataState>
      {/* 인도 점검표 대신 22종 충족 현황(11-19). WBS 가 없어도 「계획 없음」으로 보인다 */}
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
      header: '작업명',
      cell: ({ row }) => (
        <span className="block max-w-[17rem] truncate text-sm" title={row.original.name}>
          {row.original.name}
        </span>
      ),
    },
    {
      id: 'designated',
      // 예상 산출물(11-19): WBS 산출물 열의 이름과 발주기관이 요청한 산출물(UC-033)
      header: '예상 산출물',
      cell: ({ row }) => <DesignatedCell item={row.original} actions={designatedActions} />,
    },
    {
      // 판정과 업로드 자료를 한 칸으로(11-19). n/m 막대, 남은 건의 상태, 검토
      accessorKey: 'status',
      header: '업로드 상태',
      cell: ({ row }) => (
        <UploadStatusCell
          projectId={projectId}
          item={row.original}
          canReview={designatedActions.canDesignate}
          onChanged={designatedActions.onChanged}
        />
      ),
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
      header: '기한',
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
            {hasForm ? (
              <Button size="sm" disabled={busy} onClick={() => onOpenUpload(item.wbsId)}>
                {busy ? '올리는 중…' : '올리기'}
              </Button>
            ) : (
              <UploadMenu
                hasRepo={designatedActions.hasRepo}
                disabled={busy}
                label={busy ? '올리는 중…' : '올리기'}
                onFile={() => onUpload(item.wbsId)}
                onRepo={() => designatedActions.onUploadRepo(item.wbsId)}
              />
            )}
          </div>
        );
      },
    },
  ];
}

/**
 * 업로드 상태 칸(11-19). 예상 산출물 n/m 을 작은 막대로, 옆에 남은 건의 상태(「2건 지연」
 * 「1건 미제출」, 다 올라왔으면 「제출」)를 둔다. 검토 단추는 맨 앞. 수는 서버 판정이 준다.
 * 승인 현황은 칸에 두지 않는다(11-19 사용자 결정). 검토 창에서 본다.
 */
function UploadStatusCell({
  projectId,
  item,
  canReview,
  onChanged,
}: {
  projectId: string;
  item: WbsDeliverableItem;
  canReview: boolean;
  onChanged: () => void;
}): ReactNode {
  // 예상 산출물이 없는 작업은 판정할 것이 없다(11-19). 칸을 비운다
  if (item.status === 'NONE' || item.expectedTotal == null) return null;
  const total = item.expectedTotal;
  const done = item.expectedSubmitted ?? 0;
  const left = Math.max(total - done, 0);
  const label = item.status === 'SUBMITTED' ? '제출' : `${left}건 ${STATUS_LABEL[item.status]}`;
  return (
    <div className="flex items-center gap-3">
      {/* 검토는 맨 앞 고정 폭 자리에 둔다. 올라온 것이 없어 단추가 없어도 막대가 같은 자리에 선다 */}
      <div className="w-14 shrink-0">
        <ReviewButton
          projectId={projectId}
          item={item}
          canReview={canReview}
          onChanged={onChanged}
        />
      </div>
      <div className="flex min-w-0 items-center gap-2">
        <span
          className="bg-foreground/15 h-1.5 w-14 shrink-0 overflow-hidden rounded-full"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-label={`${done}/${total}건 업로드`}
        >
          <span
            className={cn('block h-full rounded-full', BAR_TONE[item.status])}
            style={{ width: `${total ? Math.round((done / total) * 100) : 0}%` }}
          />
        </span>
        <span className="tnum text-xs whitespace-nowrap">
          {done}/{total}건 업로드
        </span>
        <span
          className={cn(
            'inline-block rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
            STATUS_TONE[item.status],
          )}
        >
          {label}
        </span>
      </div>
    </div>
  );
}
