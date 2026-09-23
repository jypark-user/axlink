import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { DataState } from '@/components/common/data-state';
import { useToast } from '@/components/common/toaster';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { useAuth } from '@/features/auth/auth-context';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { formatDateTime, formatPercent } from '@/lib/format';
import { useAsync } from '@/lib/use-async';
import type {
  PageResponse,
  ReviewRequestDetailResponse,
  ReviewRequestResponse,
  ReviewRequestStatus,
  ReviewTargetOption,
  ReviewTargetType,
} from '@/types/api';

/**
 * 확인 요청 · 조치 보고 (SWFR.WEB.004~006).
 * 발주기관이 WBS 항목·산출물·이슈·리스크·지표를 짚어 요청하고, 용역사가 조치 결과를 보고하고,
 * 발주기관이 확인해 닫는다. 요청 시점의 상태와 지금 상태를 시스템이 나란히 보여 준다.
 */

const TARGET_TYPES: { value: ReviewTargetType; label: string }[] = [
  { value: 'WBS_ITEM', label: 'WBS 항목' },
  { value: 'WORK_PRODUCT', label: '산출물' },
  { value: 'ISSUE', label: '이슈' },
  { value: 'RISK', label: '리스크' },
  { value: 'METRIC', label: '지표' },
];

const TARGET_LABEL: Record<ReviewTargetType, string> = Object.fromEntries(
  TARGET_TYPES.map((t) => [t.value, t.label]),
) as Record<ReviewTargetType, string>;

const STATUS_LABEL: Record<ReviewRequestStatus, string> = {
  REQUESTED: '요청',
  REPORTED: '조치보고',
  CONFIRMED: '확인완료',
};

const STATUS_VARIANT: Record<ReviewRequestStatus, 'warning' | 'info' | 'success'> = {
  REQUESTED: 'warning',
  REPORTED: 'info',
  CONFIRMED: 'success',
};

const EVENT_LABEL: Record<string, string> = {
  REQUESTED: '요청',
  REPORTED: '조치 보고',
  CONFIRMED: '확인완료',
  REREQUESTED: '다시 요청',
};

const RATIO_FIELDS = new Set(['actual', 'declared_planned', 'value']);
const FIELD = 'flex flex-col gap-1.5';

/** 상태 값 하나를 사람이 읽는 꼴로. 비율은 퍼센트, 없으면 하이픈. */
function showValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number')
    return RATIO_FIELDS.has(field) ? formatPercent(value, 1) : String(value);
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) return formatDateTime(value);
  if (typeof value === 'string' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

function buildColumns(): ColumnDef<ReviewRequestResponse, unknown>[] {
  return [
    {
      accessorKey: 'targetLabel',
      header: ({ column }) => <SortableHeader column={column}>대상</SortableHeader>,
      cell: ({ row }) => (
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant="outline">{TARGET_LABEL[row.original.targetType]}</Badge>
          <span className="block max-w-xs truncate" title={row.original.targetLabel}>
            {row.original.targetLabel}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'title',
      header: ({ column }) => <SortableHeader column={column}>요청</SortableHeader>,
      cell: ({ row }) => (
        <span className="block max-w-sm truncate" title={row.original.title}>
          {row.original.title}
        </span>
      ),
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <SortableHeader column={column}>상태</SortableHeader>,
      cell: ({ row }) => (
        <span className="flex items-center gap-1.5">
          <Badge variant={STATUS_VARIANT[row.original.status]}>
            {STATUS_LABEL[row.original.status]}
          </Badge>
          {row.original.rerequestCount > 0 && (
            <span className="text-muted-foreground text-xs">
              재요청 {row.original.rerequestCount}
            </span>
          )}
        </span>
      ),
    },
    {
      accessorKey: 'requestedAt',
      header: ({ column }) => <SortableHeader column={column}>요청일</SortableHeader>,
      cell: ({ row }) => <span className="tnum">{formatDateTime(row.original.requestedAt)}</span>,
    },
    {
      accessorKey: 'updatedAt',
      header: ({ column }) => <SortableHeader column={column}>최근 변경</SortableHeader>,
      cell: ({ row }) => <span className="tnum">{formatDateTime(row.original.updatedAt)}</span>,
    },
  ];
}

export function ReviewRequestsPage(): ReactNode {
  const { project } = useProjectContext();
  const { me } = useAuth();
  const isClient = me?.role === 'CLIENT' || me?.role === 'SUPER_ADMIN';
  const state = useAsync<PageResponse<ReviewRequestResponse>>(
    () =>
      api.get<PageResponse<ReviewRequestResponse>>(
        `/projects/${project.id}/review-requests?size=200`,
      ),
    [project.id],
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const columns = useMemo(() => buildColumns(), []);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="확인 요청"
        description={
          isClient
            ? '확인이 필요한 항목을 짚어 요청하고, 용역사의 조치 보고를 검토합니다. 요청 시점의 상태가 함께 저장됩니다.'
            : '발주기관이 요청한 항목의 조치 결과를 보고합니다. 요청 시점과 지금의 상태 차이가 보고에 함께 붙습니다.'
        }
        actions={
          isClient ? <Button onClick={() => setCreateOpen(true)}>요청 등록</Button> : undefined
        }
      />
      <DataState
        state={state}
        empty={{
          text: isClient
            ? '등록된 확인 요청이 없습니다. 요청 등록으로 시작하십시오.'
            : '받은 확인 요청이 없습니다.',
        }}
      >
        {(page) => (
          <DataTable<ReviewRequestResponse, unknown>
            columns={columns}
            data={page.content}
            filterColumn="title"
            filterPlaceholder="요청 제목으로 찾기"
            pageSize={25}
            emptyText="확인 요청이 없습니다."
            onRowClick={(row) => setSelectedId(row.id)}
          />
        )}
      </DataState>

      <CreateDialog
        projectId={project.id}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={state.reload}
      />
      <DetailSheet
        requestId={selectedId}
        isClient={isClient}
        onClose={() => setSelectedId(null)}
        onChanged={state.reload}
      />
    </div>
  );
}

function CreateDialog({
  projectId,
  open,
  onOpenChange,
  onCreated,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [targetType, setTargetType] = useState<ReviewTargetType>('WORK_PRODUCT');
  const [targets, setTargets] = useState<ReviewTargetOption[]>([]);
  const [targetKey, setTargetKey] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [pending, setPending] = useState(false);

  // 대상 종류를 바꾸면 그 종류의 목록을 새로 받는다. 값은 전부 표준 모델에서 온다.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api
      .get<ReviewTargetOption[]>(`/projects/${projectId}/review-targets?type=${targetType}`)
      .then((list) => {
        if (!cancelled) setTargets(list);
      })
      .catch((e) => {
        if (cancelled) return;
        toast({
          title: '대상 목록을 불러오지 못했습니다.',
          description: isApiError(e) ? e.message : undefined,
          variant: 'error',
        });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId, targetType]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!targetKey) {
      toast({ title: '대상을 고르세요.', variant: 'error' });
      return;
    }
    setPending(true);
    try {
      await api.post<ReviewRequestResponse>(`/projects/${projectId}/review-requests`, {
        targetType,
        targetKey,
        title: title.trim(),
        body: body.trim(),
      });
      toast({ title: '확인 요청을 등록했습니다.', variant: 'success' });
      setTitle('');
      setBody('');
      onOpenChange(false);
      onCreated();
    } catch (err) {
      toast({
        title: '등록에 실패했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>확인 요청 등록</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className={FIELD}>
            <Label htmlFor="rrType">대상 종류</Label>
            <Select
              value={targetType}
              onValueChange={(v) => {
                setTargetType(v as ReviewTargetType);
                setTargets([]);
                setTargetKey('');
              }}
            >
              <SelectTrigger id="rrType">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TARGET_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className={FIELD}>
            <Label htmlFor="rrTarget">대상</Label>
            <Select value={targetKey} onValueChange={setTargetKey}>
              <SelectTrigger id="rrTarget">
                <SelectValue placeholder={targets.length ? '대상을 고르세요' : '대상이 없습니다'} />
              </SelectTrigger>
              <SelectContent>
                {targets.map((t) => (
                  <SelectItem key={t.key} value={t.key}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-muted-foreground text-xs">
              등록 시점의 상태(실적률·제출 여부·이슈 상태·지표값)가 요청과 함께 저장됩니다.
            </p>
          </div>
          <div className={FIELD}>
            <Label htmlFor="rrTitle">요청 제목</Label>
            <Input
              id="rrTitle"
              required
              maxLength={300}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="예: 설계서 제출 일정을 확인해 주세요"
            />
          </div>
          <div className={FIELD}>
            <Label htmlFor="rrBody">요청 내용</Label>
            <Textarea
              id="rrBody"
              rows={4}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="무엇을 확인하고 싶은지 적습니다."
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              취소
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? '등록 중' : '등록'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** 스냅샷 항목 이름. 서버 FIELD_LABELS 와 같은 표다. 바뀐 값이 없을 때는 이걸로 보인다. */
const SNAPSHOT_FIELD_LABEL: Record<string, string> = {
  status: '상태',
  severity: '심각도',
  assignee: '담당',
  owner: '담당',
  resolved_at: '해결일',
  closed_at: '종료일',
  title: '제목',
  version: '버전',
  submitted_at: '제출일',
  approved_at: '승인일',
  file_uri: '파일',
  actual: '실적률',
  declared_planned: '계획률',
  deliverable: '연결 산출물',
  end: '종료일',
  value: '값',
  numerator: '분자',
  denominator: '분모',
  level: '산정 수준',
  basis: '근거',
};

function DetailSheet({
  requestId,
  isClient,
  onClose,
  onChanged,
}: {
  requestId: string | null;
  isClient: boolean;
  onClose: () => void;
  onChanged: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [detail, setDetail] = useState<ReviewRequestDetailResponse | null>(null);
  const [note, setNote] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!requestId) return;
    let cancelled = false;
    api
      .get<ReviewRequestDetailResponse>(`/review-requests/${requestId}`)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (cancelled) return;
        toast({
          title: '요청을 불러오지 못했습니다.',
          description: isApiError(e) ? e.message : undefined,
          variant: 'error',
        });
        onClose();
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId]);

  const act = async (path: string, body: unknown, done: string) => {
    if (!detail) return;
    setPending(true);
    try {
      const next = await api.post<ReviewRequestDetailResponse>(
        `/review-requests/${detail.id}/${path}`,
        body,
      );
      setDetail(next);
      setNote('');
      toast({ title: done, variant: 'success' });
      onChanged();
    } catch (e) {
      toast({
        title: '처리에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setPending(false);
    }
  };

  const fields = detail
    ? Array.from(new Set([...Object.keys(detail.snapshot), ...Object.keys(detail.currentState)]))
    : [];
  const changed = new Set(detail?.changes.map((c) => c.field) ?? []);
  // 바뀐 값이 없으면 changes 가 비어 라벨을 못 받는다. 서버의 FIELD_LABELS 와 같은 표를 둔다
  const labelOf = (field: string) =>
    detail?.changes.find((c) => c.field === field)?.label ?? SNAPSHOT_FIELD_LABEL[field] ?? field;

  return (
    <Sheet
      open={requestId !== null}
      onOpenChange={(o) => {
        if (o) return;
        setDetail(null);
        setNote('');
        onClose();
      }}
    >
      <SheetContent className="flex w-full flex-col gap-0 overflow-y-auto sm:max-w-xl">
        {detail && (
          <>
            <SheetHeader className="gap-2 px-6 pt-6 pb-5">
              <div className="flex items-center gap-2 pr-8">
                <Badge variant="outline">{TARGET_LABEL[detail.targetType]}</Badge>
                <Badge variant={STATUS_VARIANT[detail.status]}>{STATUS_LABEL[detail.status]}</Badge>
              </div>
              <SheetTitle className="text-lg">{detail.title}</SheetTitle>
              <p className="text-muted-foreground text-sm">{detail.targetLabel}</p>
            </SheetHeader>

            <div className="flex flex-col gap-7 px-6 py-6">
              <section className="flex flex-col gap-1.5 text-sm">
                <p className="text-muted-foreground text-xs">
                  {detail.requestedByName} · {formatDateTime(detail.requestedAt)}
                </p>
                <p className="whitespace-pre-wrap">{detail.body || '(요청 내용 없음)'}</p>
              </section>

              <section className="flex flex-col gap-2.5">
                <h3 className="text-sm font-semibold">요청 시점과 지금</h3>
                <p className="text-muted-foreground text-xs">
                  {detail.changes.length === 0
                    ? '요청 이후 바뀐 값이 없습니다.'
                    : `요청 이후 ${detail.changes.length}개 값이 바뀌었습니다.`}
                </p>
                <div className="overflow-x-auto rounded border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-muted-foreground text-xs">
                      <tr>
                        <th className="px-4 py-2.5 text-left font-medium">항목</th>
                        <th className="px-4 py-2.5 text-left font-medium">요청 시점</th>
                        <th className="px-4 py-2.5 text-left font-medium">지금</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.map((f) => (
                        <tr key={f} className={changed.has(f) ? 'bg-warning-muted/40' : ''}>
                          <td className="text-muted-foreground px-4 py-2.5">{labelOf(f)}</td>
                          <td className="tnum px-4 py-2.5 break-all">
                            {showValue(f, detail.snapshot[f])}
                          </td>
                          <td className="tnum px-4 py-2.5 font-medium break-all">
                            {showValue(f, detail.currentState[f])}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {detail.reportBody && (
                <section className="flex flex-col gap-1 text-sm">
                  <h3 className="text-sm font-semibold">조치 보고</h3>
                  <p className="text-muted-foreground text-xs">
                    {detail.reportedByName} ·{' '}
                    {detail.reportedAt ? formatDateTime(detail.reportedAt) : ''}
                  </p>
                  <p className="whitespace-pre-wrap">{detail.reportBody}</p>
                </section>
              )}

              {!isClient && detail.status === 'REQUESTED' && (
                <section className="flex flex-col gap-2">
                  <Label htmlFor="rrReport">조치 결과</Label>
                  <Textarea
                    id="rrReport"
                    rows={4}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="무엇을 어떻게 조치했는지 적습니다. 상태 변화는 시스템이 옆에 붙입니다."
                  />
                  <Button
                    disabled={pending || !note.trim()}
                    onClick={() =>
                      act('report', { body: note.trim() }, '조치 결과를 보고했습니다.')
                    }
                  >
                    조치 보고
                  </Button>
                </section>
              )}

              {isClient && detail.status === 'REPORTED' && (
                <section className="flex flex-col gap-2">
                  <Label htmlFor="rrAgain">다시 요청할 내용 (미흡할 때만)</Label>
                  <Textarea
                    id="rrAgain"
                    rows={3}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="보고가 미흡하면 무엇을 더 확인해야 하는지 적습니다."
                  />
                  <div className="flex gap-2">
                    <Button
                      disabled={pending}
                      onClick={() => act('confirm', {}, '확인완료로 닫았습니다.')}
                    >
                      확인완료
                    </Button>
                    <Button
                      variant="outline"
                      disabled={pending || !note.trim()}
                      onClick={() => act('rerequest', { body: note.trim() }, '다시 요청했습니다.')}
                    >
                      다시 요청
                    </Button>
                  </div>
                </section>
              )}

              <section className="flex flex-col gap-2.5">
                <h3 className="text-sm font-semibold">이력</h3>
                <ol className="flex flex-col gap-3 text-sm">
                  {detail.events.map((ev) => (
                    <li key={ev.id} className="flex flex-col gap-1 border-l-2 py-0.5 pl-3">
                      <span className="text-muted-foreground text-xs">
                        {EVENT_LABEL[ev.kind] ?? ev.kind} · {ev.actorName} ·{' '}
                        {formatDateTime(ev.createdAt)}
                      </span>
                      {ev.body && <span className="whitespace-pre-wrap">{ev.body}</span>}
                    </li>
                  ))}
                </ol>
              </section>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
