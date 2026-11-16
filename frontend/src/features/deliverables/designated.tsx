import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ServerLink } from '@/components/common/server-link';
import { useToast } from '@/components/common/toaster';
import { isApiError } from '@/lib/api-error';
import { formatDate, formatDateTime } from '@/lib/format';
import { api } from '@/lib/http';
import { cn } from '@/lib/utils';
import { ALLOWED, rejectReason } from '@/features/documents/upload';
import type {
  DesignatedDeliverable,
  DesignatedVersion,
  DesignationEvent,
  WbsDeliverableItem,
} from '@/types/api';

/**
 * 발주기관이 WBS 작업마다 정한 산출물 항목과 양식(UC-033, 10-14 협의 「WBS 산출물」).
 * 항목(무엇을 내나)·양식(어떻게 쓰나)·제출본(낸 버전)·승인(판정)을 나눠 보인다.
 * 양식은 제출본이 아니고, 올리기만 한 문서는 확정 전까지 「등록」이다(DEC-14).
 */

const ITEM_LABEL: Record<DesignatedDeliverable['status'], string> = {
  MISSING: '미제출',
  REGISTERED: '등록(확정 전)',
  SUBMITTED: '제출',
  APPROVED: '승인',
  REJECTED: '반려',
};

const ITEM_TONE: Record<DesignatedDeliverable['status'], string> = {
  MISSING: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  REGISTERED: 'bg-muted text-muted-foreground',
  SUBMITTED: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  APPROVED: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  REJECTED: 'bg-destructive/15 text-destructive',
};

const VERSION_LABEL: Record<DesignatedVersion['state'], string> = {
  REGISTERED: '등록(확정 전)',
  SUBMITTED: '제출',
  APPROVED: '승인',
  REJECTED: '반려',
};

const EVENT_LABEL: Record<DesignationEvent['kind'], string> = {
  CREATED: '지정',
  UPDATED: '내용 고침',
  TEMPLATE: '양식 올림',
  REASSIGNED: '작업 다시 정함',
  REMOVED: '지정 거둠',
};

function base(projectId: string): string {
  return `/projects/${projectId}/wbs/designated-deliverables`;
}

function Pill({ status }: { status: DesignatedDeliverable['status'] }): ReactNode {
  return (
    <span
      className={cn(
        'inline-block rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
        ITEM_TONE[status],
      )}
    >
      {ITEM_LABEL[status]}
    </span>
  );
}

export interface DesignatedActions {
  projectId: string;
  canDesignate: boolean;
  typeNames: Record<string, string>;
  onUpload: (wbsId: string, designatedId: string) => void;
  onEdit: (target: DesignationTarget) => void;
  onChanged: () => void;
}

export type DesignationTarget =
  | { mode: 'create'; taskKey: string; taskLabel: string }
  | { mode: 'edit'; item: DesignatedDeliverable; taskLabel: string };

/** 표의 한 칸. 「내야 할 산출물 n건」과 항목별 상태·양식·제출 이력. */
export function DesignatedCell({
  item,
  actions,
}: {
  item: WbsDeliverableItem;
  actions: DesignatedActions;
}): ReactNode {
  const list = item.designated ?? [];
  const taskLabel = `${item.wbsId} ${item.name}`;
  if (list.length === 0) {
    if (!actions.canDesignate || !item.taskKey) {
      return <span className="text-muted-foreground text-sm">-</span>;
    }
    return (
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          actions.onEdit({ mode: 'create', taskKey: item.taskKey as string, taskLabel })
        }
      >
        산출물 지정
      </Button>
    );
  }
  return (
    <details className="text-sm">
      <summary className="cursor-pointer whitespace-nowrap">
        내야 할 산출물 <span className="tnum font-medium">{list.length}</span>건
      </summary>
      <ul className="mt-2 flex min-w-[20rem] flex-col gap-3">
        {list.map((d) => (
          <DesignatedEntry
            key={d.id}
            entry={d}
            wbsId={item.wbsId}
            taskLabel={taskLabel}
            actions={actions}
          />
        ))}
      </ul>
      {actions.canDesignate && item.taskKey && (
        <Button
          size="sm"
          variant="ghost"
          className="mt-1"
          onClick={() =>
            actions.onEdit({ mode: 'create', taskKey: item.taskKey as string, taskLabel })
          }
        >
          산출물 더 지정
        </Button>
      )}
    </details>
  );
}

function DesignatedEntry({
  entry,
  wbsId,
  taskLabel,
  actions,
}: {
  entry: DesignatedDeliverable;
  wbsId: string | null;
  taskLabel: string;
  actions: DesignatedActions;
}): ReactNode {
  const { toast } = useToast();
  const { projectId, canDesignate } = actions;

  const remove = async () => {
    if (!window.confirm(`「${entry.name}」 지정을 거둡니다. 제출 이력은 남습니다.`)) return;
    try {
      await api.del(`${base(projectId)}/${entry.id}`);
      toast({ title: '지정을 거뒀습니다.', variant: 'success' });
      actions.onChanged();
    } catch (err) {
      toast({
        title: '거두지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  const decide = async (v: DesignatedVersion, action: 'approve' | 'reject') => {
    let body: { reason: string } | undefined;
    const name = `${entry.name} ${v.version ?? ''}`.trim();
    if (action === 'reject') {
      const reason = window.prompt(`${name} 을(를) 반려하는 사유를 적어 주세요.`)?.trim();
      if (!reason) return;
      body = { reason };
    } else if (!window.confirm(`${name} 을(를) 승인합니다. 이 버전에만 붙습니다.`)) {
      return;
    }
    try {
      await api.post(
        `/projects/${projectId}/work-products/${v.workProductId}/${action}`,
        body ?? {},
      );
      toast({
        title: action === 'approve' ? '승인했습니다.' : '반려했습니다.',
        variant: 'success',
      });
      actions.onChanged();
    } catch (err) {
      toast({
        title: action === 'approve' ? '승인하지 못했습니다.' : '반려하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <li className="border-border flex flex-col gap-1 border-l-2 pl-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-medium">{entry.name}</span>
        <Pill status={entry.status} />
        {entry.productType && (
          <span className="text-muted-foreground text-xs">
            {actions.typeNames[entry.productType] ?? entry.productType}
          </span>
        )}
      </div>
      {entry.description && <p className="text-muted-foreground text-xs">{entry.description}</p>}
      {entry.guide && <p className="text-muted-foreground text-xs">작성 안내: {entry.guide}</p>}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {entry.templateFileName ? (
          <ServerLink
            url={`/api${base(projectId)}/${entry.id}/template`}
            filename={entry.templateFileName}
            className="underline-offset-2 hover:underline"
            title="양식 내려받기. 양식은 제출본이 아닙니다"
          >
            양식 내려받기: {entry.templateFileName}
          </ServerLink>
        ) : (
          <span className="text-muted-foreground">양식 없음</span>
        )}
        {wbsId && !entry.needsRedesignation && (
          <Button size="sm" variant="outline" onClick={() => actions.onUpload(wbsId, entry.id)}>
            {entry.versions.length > 0 ? '새 버전 제출' : '제출할 파일 올리기'}
          </Button>
        )}
        {canDesignate && (
          <>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => actions.onEdit({ mode: 'edit', item: entry, taskLabel })}
            >
              고치기
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void remove()}>
              거두기
            </Button>
          </>
        )}
      </div>
      {entry.versions.length > 0 && (
        <ul className="text-muted-foreground flex flex-col gap-1 text-xs">
          {entry.versions.map((v) => (
            <li key={v.documentId} className="flex flex-wrap items-center gap-1.5">
              <span className="tnum">{v.version ?? '-'}</span>
              <span>{v.fileName}</span>
              <span>· {VERSION_LABEL[v.state]}</span>
              <span>· {formatDateTime(v.uploadedAt)}</span>
              {v.decidedAt && <span>· 승인 {formatDate(v.decidedAt)}</span>}
              {v.rejectReason && (
                <span className="text-destructive">· 반려 사유: {v.rejectReason}</span>
              )}
              {canDesignate && v.isCurrent && v.state === 'SUBMITTED' && v.workProductId && (
                <>
                  <Button size="sm" variant="outline" onClick={() => void decide(v, 'approve')}>
                    승인
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void decide(v, 'reject')}>
                    반려
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <History projectId={projectId} id={entry.id} />
    </li>
  );
}

function History({ projectId, id }: { projectId: string; id: string }): ReactNode {
  const [events, setEvents] = useState<DesignationEvent[] | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open || events) return;
    api
      .get<DesignationEvent[]>(`${base(projectId)}/${id}/history`)
      .then(setEvents)
      .catch(() => setEvents([]));
  }, [open, events, projectId, id]);
  return (
    <details
      className="text-muted-foreground text-xs"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer">지정 변경 이력</summary>
      {events === null ? (
        <p className="mt-1">불러오는 중…</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-0.5">
          {events.map((e, i) => (
            <li key={`${e.at}-${i}`}>
              {formatDateTime(e.at)} · {EVENT_LABEL[e.kind]} · {e.actorName}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

/** 계획서 교체로 작업이 끊긴 지정 항목. 지우지 않고 모아 두고 발주기관이 작업을 다시 정한다. */
export function RedesignationPanel({
  entries,
  tasks,
  actions,
}: {
  entries: DesignatedDeliverable[];
  tasks: WbsDeliverableItem[];
  actions: DesignatedActions;
}): ReactNode {
  const { toast } = useToast();
  const [choice, setChoice] = useState<Record<string, string>>({});
  if (entries.length === 0) return null;
  const leafTasks = tasks.filter((t) => t.taskKey);

  const reassign = async (entry: DesignatedDeliverable) => {
    const taskKey = choice[entry.id];
    if (!taskKey) return;
    try {
      await api.patch(`${base(actions.projectId)}/${entry.id}`, { taskKey });
      toast({ title: '작업을 다시 정했습니다.', variant: 'success' });
      actions.onChanged();
    } catch (err) {
      toast({
        title: '다시 정하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <section className="border-destructive/40 bg-destructive/5 mb-4 rounded-md border p-3 text-sm">
      <h2 className="font-medium">재지정 필요 {entries.length}건</h2>
      <p className="text-muted-foreground mb-2 text-xs">
        계획서가 바뀌어 지정했던 작업을 찾지 못했습니다. 지정과 제출 이력은 그대로 있습니다.
        {actions.canDesignate
          ? ' 지금 계획서의 작업을 골라 다시 정하세요.'
          : ' 발주기관이 작업을 다시 정합니다.'}
      </p>
      <ul className="flex flex-col gap-3">
        {entries.map((entry) => (
          <li key={entry.id} className="flex flex-col gap-1">
            <span className="text-muted-foreground text-xs">
              예전 작업: {entry.wbsIdAt} {entry.taskNameAt}
            </span>
            <DesignatedEntry
              entry={entry}
              wbsId={null}
              taskLabel={`${entry.wbsIdAt} ${entry.taskNameAt}`}
              actions={actions}
            />
            {actions.canDesignate && (
              <div className="flex items-center gap-2">
                <select
                  aria-label={`${entry.name} 다시 정할 작업`}
                  className="border-input bg-background h-8 rounded-md border px-2 text-sm"
                  value={choice[entry.id] ?? ''}
                  onChange={(e) => setChoice((c) => ({ ...c, [entry.id]: e.target.value }))}
                >
                  <option value="">작업 고르기</option>
                  {leafTasks.map((t) => (
                    <option key={t.taskKey as string} value={t.taskKey as string}>
                      {t.wbsId} {t.name}
                    </option>
                  ))}
                </select>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!choice[entry.id]}
                  onClick={() => void reassign(entry)}
                >
                  다시 정하기
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** 지정하기·고치기. 양식 파일은 저장 뒤 따로 올린다(양식은 제출본이 아니다). */
export function DesignateDialog({
  projectId,
  target,
  typeNames,
  onClose,
  onDone,
}: {
  projectId: string;
  target: DesignationTarget;
  typeNames: Record<string, string>;
  onClose: () => void;
  onDone: () => void;
}): ReactNode {
  const { toast } = useToast();
  const initial = target.mode === 'edit' ? target.item : null;
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [productType, setProductType] = useState(initial?.productType ?? '');
  const [guide, setGuide] = useState(initial?.guide ?? '');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return setError('산출물 이름을 적으세요.');
    if (file) {
      const reason = rejectReason(file);
      if (reason) return setError(reason);
    }
    setBusy(true);
    setError(null);
    const body = {
      name: name.trim(),
      description: description.trim() || null,
      productType: productType || null,
      guide: guide.trim() || null,
    };
    try {
      let id: string;
      if (target.mode === 'create') {
        const res = await api.post<{ id: string }>(base(projectId), {
          ...body,
          taskKey: target.taskKey,
        });
        id = res.id;
      } else {
        id = target.item.id;
        await api.patch(`${base(projectId)}/${id}`, body);
      }
      if (file) {
        const form = new FormData();
        form.append('file', file);
        await api.upload(`${base(projectId)}/${id}/template`, form);
      }
      toast({ title: '산출물 지정을 저장했습니다.', variant: 'success' });
      onDone();
    } catch (err) {
      setError(isApiError(err) ? err.message : '저장하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const types = Object.entries(typeNames);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{target.mode === 'create' ? '산출물 지정' : '지정 고치기'}</DialogTitle>
            <DialogDescription>
              {target.taskLabel} 작업에서 용역사가 내야 할 산출물과 양식을 정합니다. 양식은
              제출본으로 세지 않습니다.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dd-name">산출물 이름</Label>
            <Input id="dd-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dd-type">분류 (선택)</Label>
            <select
              id="dd-type"
              className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              value={productType}
              onChange={(e) => setProductType(e.target.value)}
            >
              <option value="">분류 없음</option>
              {types.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dd-desc">설명 (선택)</Label>
            <Textarea
              id="dd-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dd-guide">작성 안내 (선택)</Label>
            <Textarea
              id="dd-guide"
              rows={2}
              value={guide}
              onChange={(e) => setGuide(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dd-file">
              양식 파일 (선택
              {initial?.templateFileName ? `, 지금: ${initial.templateFileName}` : ''})
            </Label>
            <Input
              id="dd-file"
              type="file"
              accept={ALLOWED.join(',')}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              그만두기
            </Button>
            <Button type="submit" disabled={busy}>
              저장
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
