import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Download, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ServerLink } from '@/components/common/server-link';
import { useToast } from '@/components/common/toaster';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
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

/**
 * 작업의 검토 상태 한 마디. 지난 판(같은 양식에 다시 올린 것의 앞 판)은 보지 않는다.
 * 하나라도 승인 대기면 승인 대기, 모두 승인이면 승인, 아니면 반려
 */
export function reviewState(
  list: DeliverableReview[],
): 'SUBMITTED' | 'APPROVED' | 'REJECTED' | null {
  const live = list.filter((r) => r.latest);
  if (live.length === 0) return null;
  if (live.some((r) => r.status === 'SUBMITTED')) return 'SUBMITTED';
  if (live.every((r) => r.status === 'APPROVED')) return 'APPROVED';
  return 'REJECTED';
}

/** 판정 칸에 붙는 승인 상태 딱지. 올라온 산출물이 없으면 그리지 않는다 */
export function ReviewBadge({ item }: { item: WbsDeliverableItem }): ReactNode {
  const state = reviewState(item.review ?? []);
  if (state === null) return null;
  return (
    <span
      className={cn(
        'inline-block rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
        STATUS_TONE[state],
      )}
    >
      {STATUS_TEXT[state]}
    </span>
  );
}

/**
 * 산출물 줄의 검토(11-18 사용자 결정: 승인 단위는 올라온 산출물). 올리기 왼쪽에 둔다. 발주기관은
 * 눌러 그 작업에 올라온 산출물 하나하나를 승인·반려한다. 용역사는 판정 칸의 상태만 본다.
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
  if (!canReview || list.length === 0) return null;
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        검토
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
                key={r.documentId}
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

  const decide = async (action: 'approve' | 'reject') => {
    let body: { reason: string } | undefined;
    if (action === 'reject') {
      const reason = window.prompt(`${r.fileName} 을(를) 반려하는 사유를 적어 주세요.`)?.trim();
      if (!reason) return;
      body = { reason };
    }
    setBusy(true);
    try {
      await api.post(`/projects/${projectId}/documents/${r.documentId}/${action}`, body ?? {});
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
    <li
      className={cn(
        'flex min-w-0 flex-col gap-1.5 rounded-md border px-3 py-2',
        !r.latest && 'opacity-70',
      )}
    >
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
        {!r.latest && <span className="text-muted-foreground text-xs">지난 판</span>}
      </div>
      {/* 파일 이름을 누르면 원문(자료 상세)으로, 옆 단추로 내려받는다 */}
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <Link
          to={`/p/${projectId}/documents/${r.documentId}`}
          className="text-primary inline-flex min-w-0 items-center gap-1 underline-offset-2 hover:underline"
          title="원문 보기"
        >
          <span className="truncate">{r.fileName}</span>
          <ExternalLink className="size-3 shrink-0" />
        </Link>
        <ServerLink
          url={`/api/documents/${r.documentId}/content`}
          filename={r.fileName}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
          title="파일 내려받기"
        >
          <Download className="size-3.5" />
          내려받기
        </ServerLink>
        <span className="text-muted-foreground tnum">{formatDateTime(r.uploadedAt)}</span>
      </div>
      {r.rejectReason && <p className="text-destructive text-xs">반려 사유: {r.rejectReason}</p>}
      <div className="flex justify-end gap-2">
        {r.status !== 'APPROVED' && (
          <Button size="sm" disabled={busy} onClick={() => void decide('approve')}>
            승인
          </Button>
        )}
        {r.status !== 'REJECTED' && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void decide('reject')}>
            반려
          </Button>
        )}
      </div>
    </li>
  );
}
