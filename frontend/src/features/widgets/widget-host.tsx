import { useState, type ReactNode } from 'react';
import { GripVertical, Info, Pencil, RefreshCw, Trash2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { api } from '@/lib/http';
import { isApiError } from '@/lib/api-error';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import { resolveWidgetRenderer } from '@/features/widgets/renderer-registry';
import type { WidgetDataResponse, WidgetResponse } from '@/types/api';

export function WidgetHost({
  widget,
  editing,
  onDelete,
  onEdit,
}: {
  widget: WidgetResponse;
  editing: boolean;
  onDelete?: (widgetId: string) => void;
  onEdit?: (widget: WidgetResponse) => void;
}): ReactNode {
  const state = useAsync<WidgetDataResponse>(
    () => api.post<WidgetDataResponse>(`/widgets/${widget.id}/data`, {}),
    [widget.id, widget.updatedAt],
  );
  /** 삭제는 저장과 무관하게 즉시다 — 되돌릴 수 없으니 한 번은 묻는다. */
  const [confirming, setConfirming] = useState(false);
  /** 산출 근거를 펼쳐 둔 상태. 지표마다 근거가 붙는다 (QUR.WEB.002) — 늘 펴 두면 그림이 밀려 누르면 보인다. */
  const [basisOpen, setBasisOpen] = useState(false);
  const basis = state.data?.basis ?? null;
  const Renderer = resolveWidgetRenderer(widget.spec?.template ?? widget.template);
  const title = widget.spec?.title ?? widget.title;
  const empty = state.data !== null && state.data.rows.length === 0 && state.data.total === null;

  return (
    <Card
      className={cn(
        'flex h-full flex-col overflow-hidden',
        // 편집 중에는 카드가 "잡을 수 있는 블록" 으로 보여야 한다 — 테두리로 말하고, 손을 올리면 짙어진다.
        editing &&
          'ring-primary/25 hover:ring-primary/60 cursor-grab ring-1 transition-shadow select-none active:cursor-grabbing',
      )}
    >
      <CardHeader>
        <CardTitle className="flex min-w-0 items-center gap-1.5 text-sm">
          {editing && <GripVertical className="text-muted-foreground/70 size-4 shrink-0" />}
          <span className="truncate">{title}</span>
        </CardTitle>
        <CardDescription className="truncate text-xs">
          {state.data
            ? `${state.data.measureLabel} · 프로젝트 ${state.data.appliedProjectIds.length}개`
            : ' '}
        </CardDescription>
        <CardAction className="flex items-center gap-1">
          {/* 편집 중에는 배치가 일이다 — 새로고침은 치우고 삭제만 남긴다. */}
          {!editing && basis && (
            <Button
              size="icon"
              variant="ghost"
              aria-label="산출 근거"
              aria-pressed={basisOpen}
              className={cn(basisOpen && 'text-primary')}
              onClick={() => setBasisOpen((v) => !v)}
            >
              <Info className="size-4" />
            </Button>
          )}
          {!editing && (
            <Button size="icon" variant="ghost" aria-label="새로고침" onClick={state.reload}>
              <RefreshCw className="size-4" />
            </Button>
          )}
          {editing && onEdit && (
            <Button
              size="icon"
              variant="ghost"
              aria-label="위젯 수정"
              // 카드 전체가 드래그 손잡이라 버튼 위에서는 끌기가 시작되지 않게 막는다.
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => onEdit(widget)}
            >
              <Pencil className="size-4" />
            </Button>
          )}
          {editing && onDelete && (
            <Button
              size="icon"
              variant="ghost"
              aria-label="위젯 삭제"
              className="hover:text-destructive"
              onClick={() => setConfirming(true)}
            >
              <Trash2 className="size-4" />
            </Button>
          )}
        </CardAction>
      </CardHeader>
      <CardContent
        className={cn(
          'min-h-0 flex-1 overflow-auto',
          // 끌다가 차트 툴팁·표 버튼이 반응하면 배치에 방해만 된다 — 편집 중 내용은 그림일 뿐이다.
          editing && 'pointer-events-none',
        )}
      >
        {state.loading && state.data === null && <Skeleton className="h-24 w-full" />}
        {state.error !== null && (
          <Alert variant="destructive">
            <AlertTitle>위젯을 불러오지 못했습니다</AlertTitle>
            <AlertDescription>
              {isApiError(state.error) && state.error.status === 403
                ? '이 프로젝트의 대시보드 열람 권한이 없습니다.'
                : isApiError(state.error)
                  ? state.error.message
                  : '알 수 없는 오류'}
              <Button size="sm" variant="outline" className="mt-2" onClick={state.reload}>
                재시도
              </Button>
            </AlertDescription>
          </Alert>
        )}
        {state.error === null && empty && (
          <p className="text-muted-foreground py-6 text-center text-sm">
            조건에 맞는 데이터가 없습니다.
          </p>
        )}
        {state.error === null && state.data !== null && !empty && (
          <Renderer spec={widget.spec} data={state.data} />
        )}
      </CardContent>
      {!editing && basisOpen && basis && (
        <div className="border-border mx-4 mb-3 rounded-md border bg-muted/40 px-3 py-2">
          <p className="text-muted-foreground text-xs font-semibold tracking-wide">산출 근거</p>
          <p className="text-foreground mt-1 text-xs leading-relaxed" data-testid="widget-basis">
            {basis}
          </p>
        </div>
      )}
      {state.data?.truncated && (
        <div className="px-4 pb-2">
          <Badge variant="warning">상위 {state.data.rows.length}건만 표시</Badge>
        </div>
      )}

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>‘{title}’ 위젯을 삭제할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              저장 버튼과 무관하게 바로 지워지고, 되돌릴 수 없습니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>남겨두기</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90 text-white"
              onClick={() => onDelete?.(widget.id)}
            >
              삭제
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
