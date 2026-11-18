import { useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/common/toaster';
import { isApiError } from '@/lib/api-error';
import { api } from '@/lib/http';
import { cn } from '@/lib/utils';
import type { DeliverableReview, WbsDeliverableItem } from '@/types/api';

const STATUS_TEXT: Record<string, string> = {
  SUBMITTED: '승인 대기',
  APPROVED: '승인',
  REJECTED: '반려',
};

const STATUS_TONE: Record<string, string> = {
  SUBMITTED: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  APPROVED: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  REJECTED: 'bg-destructive/15 text-destructive',
};

/** 작업의 검토 상태 한 마디. 하나라도 승인 대기면 승인 대기, 모두 승인이면 승인, 아니면 반려 */
export function reviewState(
  list: DeliverableReview[],
): 'SUBMITTED' | 'APPROVED' | 'REJECTED' | null {
  if (list.length === 0) return null;
  if (list.some((r) => r.status === 'SUBMITTED')) return 'SUBMITTED';
  if (list.every((r) => r.status === 'APPROVED')) return 'APPROVED';
  return 'REJECTED';
}

/**
 * 산출물 줄의 검토(11-18 사용자 지시). 올리기 왼쪽에 둔다. 발주기관은 눌러 올라온 제출본을
 * 승인·반려하고, 용역사는 상태만 본다. 양식은 양식 창에서, 제출본 검토는 여기서만 한다.
 */
export function ReviewButton({
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
  const [open, setOpen] = useState(false);
  const list = item.review ?? [];
  const state = reviewState(list);
  if (state === null) return null;
  if (!canReview) {
    return (
      <span
        className={cn(
          'rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
          STATUS_TONE[state],
        )}
      >
        {STATUS_TEXT[state]}
      </span>
    );
  }
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className={cn(state === 'SUBMITTED' && 'border-sky-500/60')}
        onClick={() => setOpen(true)}
      >
        {STATUS_TEXT[state]}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>산출물 검토</DialogTitle>
            <DialogDescription>
              {item.wbsId} {item.name}
            </DialogDescription>
          </DialogHeader>
          <ul className="flex min-w-0 flex-col gap-3">
            {list.map((r) => (
              <ReviewRow
                key={r.workProductId}
                projectId={projectId}
                review={r}
                onChanged={onChanged}
              />
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ReviewRow({
  projectId,
  review: r,
  onChanged,
}: {
  projectId: string;
  review: DeliverableReview;
  onChanged: () => void;
}): ReactNode {
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);
  const label = `${r.name}${r.version ? ` ${r.version}` : ''}`;

  const decide = async (action: 'approve' | 'reject') => {
    let body: { reason: string } | undefined;
    if (action === 'reject') {
      const reason = window.prompt(`${label} 을(를) 반려하는 사유를 적어 주세요.`)?.trim();
      if (!reason) return;
      body = { reason };
    }
    setBusy(true);
    try {
      await api.post(
        `/projects/${projectId}/work-products/${r.workProductId}/${action}`,
        body ?? {},
      );
      toast({
        title: action === 'approve' ? '승인했습니다.' : '반려했습니다.',
        variant: 'success',
      });
      onChanged();
    } catch (err) {
      toast({
        title: action === 'approve' ? '승인하지 못했습니다.' : '반려하지 못했습니다.',
        description: isApiError(err) ? err.message : undefined,
        variant: 'error',
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="flex min-w-0 flex-col gap-1.5 rounded-md border px-3 py-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="font-medium">{r.name}</span>
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
            STATUS_TONE[r.status],
          )}
        >
          {STATUS_TEXT[r.status] ?? r.status}
        </span>
      </div>
      <div className="text-muted-foreground flex min-w-0 flex-wrap gap-x-3 text-xs">
        {r.fileName && <span className="truncate">{r.fileName}</span>}
        {r.version && <span className="tnum">버전 {r.version}</span>}
      </div>
      {r.rejectReason && r.status === 'REJECTED' && (
        <p className="text-destructive text-xs">반려 사유: {r.rejectReason}</p>
      )}
      {r.isCurrent ? (
        <div className="flex gap-2">
          {r.status === 'SUBMITTED' && (
            <Button size="sm" disabled={busy} onClick={() => void decide('approve')}>
              승인
            </Button>
          )}
          {r.status !== 'REJECTED' && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => void decide('reject')}
            >
              반려
            </Button>
          )}
        </div>
      ) : (
        <p className="text-muted-foreground text-xs">
          같은 분류의 새 버전이 올라와 있어 이 버전은 승인·반려할 수 없습니다.
        </p>
      )}
    </li>
  );
}
