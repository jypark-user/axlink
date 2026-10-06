import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { api } from '@/lib/http';
import { formatDateTime } from '@/lib/format';
import type { ActivityEventResponse, NotificationsResponse } from '@/types/api';

/** 활동 종류 라벨. 서버는 코드만 준다. */
const KIND_LABEL: Record<string, string> = {
  REVIEW_REQUESTED: '확인 요청',
  REVIEW_REPORTED: '조치 보고',
  REVIEW_CONFIRMED: '확인완료',
  REVIEW_REREQUESTED: '다시 요청',
  DOCUMENT_UPLOADED: '문서',
  DELIVERABLE_SUBMITTED: '산출물 제출',
  DELIVERABLE_OVERDUE: '산출물 지연',
  WORK_PRODUCT_APPROVED: '산출물 승인',
  WORK_PRODUCT_REJECTED: '산출물 반려',
  SYNC_FAILED: '동기화 실패',
  SYNC_CHANGED: '동기화 변경',
  SNAPSHOT_TAKEN: '스냅샷 기록',
};

const POLL_MS = 60_000;

/** 활동 한 줄이 가리키는 화면. 대상이 없으면 사업 활동 탭으로. */
export function pathFor(e: ActivityEventResponse): string {
  const base = `/p/${e.projectId}`;
  switch (e.targetType) {
    case 'REVIEW_REQUEST':
      return `${base}/reviews?open=${e.targetKey ?? ''}`;
    case 'DOCUMENT':
      return `${base}/documents/${e.targetKey ?? ''}`;
    case 'WBS_ITEM':
      return `${base}/deliverables`;
    case 'SYNC_JOB':
      return `${base}/collection`;
    default:
      return base;
  }
}

/**
 * 머리줄의 종. 내 역할이 알아야 할 최근 활동과 미읽음 수를 60초마다 묻는다.
 * 열면 읽은 것으로 표시한다. 폐쇄망이라 앱 안에서만 알린다.
 */
export function NotificationBell(): ReactNode {
  const navigate = useNavigate();
  const [data, setData] = useState<NotificationsResponse | null>(null);
  const [open, setOpen] = useState(false);

  const load = async () => {
    try {
      setData(await api.get<NotificationsResponse>('/notifications?size=20'));
    } catch {
      // 알림은 부가 기능이다. 실패해도 화면을 흔들지 않는다
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  const onOpenChange = async (next: boolean) => {
    setOpen(next);
    if (next && data && data.unread > 0) {
      try {
        await api.post('/notifications/seen', {});
        setData({ ...data, unread: 0 });
      } catch {
        // 읽음 표시 실패는 다음 폴링에서 다시 맞춘다
      }
    }
  };

  const unread = data?.unread ?? 0;
  const items = data?.items ?? [];

  return (
    <DropdownMenu open={open} onOpenChange={(v) => void onOpenChange(v)}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="알림">
          <Bell className="size-4" />
          {unread > 0 && (
            <span className="bg-destructive text-destructive-foreground tnum absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-96 max-w-[calc(100vw-2rem)]">
        <DropdownMenuLabel>알림</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {items.length === 0 ? (
          <p className="text-muted-foreground px-2 py-3 text-sm">새 소식이 없습니다.</p>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            {items.map((e) => (
              <DropdownMenuItem
                key={e.id}
                className="flex cursor-pointer flex-col items-start gap-0.5 py-2"
                onSelect={() => void navigate(pathFor(e))}
              >
                <span className="text-muted-foreground text-xs">
                  {KIND_LABEL[e.kind] ?? e.kind} · {e.actorLabel} · {formatDateTime(e.occurredAt)}
                </span>
                <span className="text-sm leading-snug">{e.summary}</span>
                <span className="text-muted-foreground text-xs">{e.projectName}</span>
              </DropdownMenuItem>
            ))}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
