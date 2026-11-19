import { useState, type ReactNode } from 'react';
import { ArrowLeft, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Markdown } from '@/components/ui/markdown';
import { DataState } from '@/components/common/data-state';
import { ServerLink } from '@/components/common/server-link';
import { useToast } from '@/components/common/toaster';
import { isApiError } from '@/lib/api-error';
import { formatDateTime } from '@/lib/format';
import { api } from '@/lib/http';
import { useAsync } from '@/lib/use-async';
import { cn } from '@/lib/utils';
import type { DeliverableReview, DocumentTextResponse, WbsDeliverableItem } from '@/types/api';

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
 * 작업에 올라온 산출물을 상태별로 센다. 지난 버전(같은 양식에 다시 올린 것의 앞 판)은 세지 않는다
 */
export function reviewCounts(
  list: DeliverableReview[],
): Record<DeliverableReview['status'], number> {
  const counts = { SUBMITTED: 0, APPROVED: 0, REJECTED: 0 };
  for (const r of list) if (r.latest) counts[r.status] += 1;
  return counts;
}

const COUNT_TONE: Record<string, string> = {
  SUBMITTED: 'text-sky-700 dark:text-sky-300',
  APPROVED: 'text-emerald-700 dark:text-emerald-300',
  REJECTED: 'text-destructive',
};

/** 판정 칸의 승인 현황(11-19). 「승인 대기 n건」「승인 m건」「반려 k건」, 0건은 그리지 않는다 */
export function ReviewBadge({ item }: { item: WbsDeliverableItem }): ReactNode {
  const counts = reviewCounts(item.review ?? []);
  const shown = (['SUBMITTED', 'APPROVED', 'REJECTED'] as const).filter((k) => counts[k] > 0);
  if (shown.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-x-2 text-xs font-medium">
      {shown.map((k) => (
        <span key={k} className={cn('whitespace-nowrap', COUNT_TONE[k])}>
          {STATUS_TEXT[k]} {counts[k]}건
        </span>
      ))}
    </span>
  );
}

/** 같은 예상 산출물에 이어 올린 버전들(최근 것이 앞). 예상 산출물 없이 올린 것은 그 하나뿐이다 */
function versionsOf(list: DeliverableReview[], r: DeliverableReview): DeliverableReview[] {
  return r.designatedId ? list.filter((x) => x.designatedId === r.designatedId) : [r];
}

/**
 * 산출물 줄의 검토(11-18 사용자 결정: 승인 단위는 올라온 산출물). 올리기 왼쪽에 둔다. 발주기관은
 * 눌러 그 작업에 올라온 산출물 하나하나를 승인·반려한다. 용역사는 판정 칸의 상태만 본다.
 * 목록에는 최신 버전만 둔다. 지난 버전은 그 최신 버전의 상세보기에서 원문과 함께 본다(11-19).
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
  const [detailId, setDetailId] = useState<string | null>(null);
  const list = item.review ?? [];
  if (!canReview || list.length === 0) return null;
  const latest = list.filter((r) => r.latest);
  const target = latest.find((r) => r.documentId === detailId) ?? null;
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        검토
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setDetailId(null);
        }}
      >
        <DialogContent
          className={cn('max-h-[85vh] overflow-y-auto', target ? 'sm:max-w-3xl' : 'sm:max-w-xl')}
        >
          <DialogHeader>
            <DialogTitle>{target ? target.name : '산출물 검토'}</DialogTitle>
            <DialogDescription>
              {item.wbsId} {item.name}
            </DialogDescription>
          </DialogHeader>
          {target ? (
            <ReviewDetail
              key={target.documentId}
              versions={versionsOf(list, target)}
              onBack={() => setDetailId(null)}
            />
          ) : (
            <ul className="flex min-w-0 flex-col gap-3">
              {latest.map((r) => (
                <ReviewRow
                  key={r.documentId}
                  projectId={projectId}
                  review={r}
                  older={versionsOf(list, r).length - 1}
                  onDetail={() => setDetailId(r.documentId)}
                  onChanged={onChanged}
                />
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusTag({ status }: { status: DeliverableReview['status'] }): ReactNode {
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
        STATUS_TONE[status],
      )}
    >
      {STATUS_TEXT[status] ?? status}
    </span>
  );
}

function DownloadLink({ review: r }: { review: DeliverableReview }): ReactNode {
  return (
    <ServerLink
      url={`/api/documents/${r.documentId}/content`}
      filename={r.fileName}
      className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
      title="파일 내려받기"
    >
      <Download className="size-3.5" />
      내려받기
    </ServerLink>
  );
}

function ReviewRow({
  projectId,
  review: r,
  older,
  onDetail,
  onChanged,
}: {
  projectId: string;
  review: DeliverableReview;
  older: number;
  onDetail: () => void;
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
    <li className="flex min-w-0 flex-col gap-1.5 rounded-md border px-3 py-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="font-medium">{r.name}</span>
        <StatusTag status={r.status} />
        {older > 0 && <span className="text-muted-foreground text-xs">지난 버전 {older}개</span>}
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="min-w-0 truncate">{r.fileName}</span>
        <DownloadLink review={r} />
        <span className="text-muted-foreground tnum">{formatDateTime(r.uploadedAt)}</span>
      </div>
      {r.rejectReason && <p className="text-destructive text-xs">반려 사유: {r.rejectReason}</p>}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onDetail}>
          상세보기
        </Button>
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

/** 상세보기. 위에 버전 목록(최신이 앞), 아래에 고른 버전의 원문. 읽기만 한다 */
function ReviewDetail({
  versions,
  onBack,
}: {
  versions: DeliverableReview[];
  onBack: () => void;
}): ReactNode {
  const [selected, setSelected] = useState(versions[0]?.documentId ?? '');
  const current = versions.find((v) => v.documentId === selected) ?? versions[0];
  const text = useAsync<DocumentTextResponse>(
    () => api.get<DocumentTextResponse>(`/documents/${selected}/text`),
    [selected],
  );
  if (!current) return null;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div>
        <Button size="sm" variant="ghost" onClick={onBack}>
          <ArrowLeft />
          목록
        </Button>
      </div>
      {/* 버전이 늘어도 창이 길어지지 않게 세 줄까지만 보이고 나머지는 이 안에서 내린다 */}
      <ul className="flex max-h-[7.25rem] min-w-0 flex-col gap-1 overflow-y-auto pr-1">
        {versions.map((v, i) => (
          <li key={v.documentId}>
            <button
              type="button"
              aria-pressed={v.documentId === current.documentId}
              onClick={() => setSelected(v.documentId)}
              className={cn(
                'flex h-9 w-full min-w-0 items-center gap-3 rounded-md border px-3 text-left text-xs',
                v.documentId === current.documentId
                  ? 'border-primary bg-primary/5'
                  : 'hover:bg-muted/50',
              )}
            >
              <span className="text-muted-foreground w-8 shrink-0">{i === 0 ? '최신' : 'old'}</span>
              <span className="min-w-0 flex-1 truncate font-medium">{v.fileName}</span>
              <StatusTag status={v.status} />
              <span className="text-muted-foreground tnum shrink-0 whitespace-nowrap">
                {formatDateTime(v.uploadedAt)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <DownloadLink review={current} />
        {current.reviewedAt && (
          <span className="text-muted-foreground tnum">
            {STATUS_TEXT[current.status]} {formatDateTime(current.reviewedAt)}
          </span>
        )}
      </div>
      {current.rejectReason && (
        <p className="text-destructive text-xs">반려 사유: {current.rejectReason}</p>
      )}
      <DataState state={text} onRetry={text.reload} empty={{ text: '추출된 글이 없습니다.' }}>
        {(t) =>
          t.text.trim() ? (
            <div className="max-h-[50vh] overflow-y-auto rounded border p-4">
              <Markdown className="text-sm leading-6">{t.text}</Markdown>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">추출된 글이 없습니다.</p>
          )
        }
      </DataState>
    </div>
  );
}
