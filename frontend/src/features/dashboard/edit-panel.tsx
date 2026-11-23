import { useState, type ReactNode } from 'react';
import { Check, LayoutTemplate, Loader2, RotateCcw, Trash2, X } from 'lucide-react';
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
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { isApiError } from '@/lib/api-error';
import { label as labelOf } from '@/lib/labels';
import { cn } from '@/lib/utils';
import {
  DASHBOARD_PRESETS,
  DEFAULT_PRESET,
  type DashboardPreset,
} from '@/features/dashboard/dashboard-presets';
import { applyPreset, clearWidgets } from '@/features/dashboard/preset-apply';
import { WidgetSketch } from '@/features/dashboard/widget-sketch';
import { widgetRenderers } from '@/features/widgets/renderer-registry';
import type { WidgetResponse, WidgetTemplate } from '@/types/api';

/**
 * 위젯 팔레트의 순서 — 등록 순서(만든 순서)가 아니라 데이터 모양별로 묶는다.
 * 고르는 사람의 질문은 "막대였나 선이었나"가 아니라 "지금 값인가, 흐름인가, 분포인가"다.
 */
const TEMPLATE_GROUPS: { label: string; items: WidgetTemplate[] }[] = [
  { label: '수치', items: ['STAT_CARD', 'SPARKLINE', 'BULLET_CHART'] },
  {
    label: '추이',
    items: [
      'LINE_CHART',
      'AREA_CHART',
      'CUMULATIVE_FLOW',
      'SLOPE_CHART',
      'BUMP_CHART',
      'CALENDAR_HEATMAP',
    ],
  },
  {
    label: '분포',
    items: [
      'BAR_CHART',
      'HORIZONTAL_BAR_CHART',
      'STACKED_BAR_CHART',
      'PARETO',
      'HEATMAP',
      'TREEMAP',
    ],
  },
  { label: '구성', items: ['PIE_CHART', 'DONUT_CHART', 'STATUS_FLOW', 'RADAR_CHART'] },
  { label: '목록', items: ['PROGRESS_LIST', 'DATA_TABLE', 'CHECKLIST', 'GANTT_SUMMARY'] },
];

/** 위 목록에 아직 안 넣은 템플릿 — 새로 등록돼도 팔레트에서 사라지지 않게 뒤에 붙인다. */
const UNGROUPED = (Object.keys(widgetRenderers) as WidgetTemplate[]).filter(
  (t) => !TEMPLATE_GROUPS.some((g) => g.items.includes(t)),
);

const CARD =
  'border-border hover:border-ring hover:bg-accent flex flex-col items-start justify-center gap-1 rounded-md border border-dashed p-3 text-left transition-colors disabled:opacity-50';

/**
 * 화면을 바꾸기 전에 확인받는 일들. 초기화는 기본 구성으로 되돌리는 것이고(11-18 사용자 지시),
 * 위젯을 모두 치우기만 하는 것은 「전체 삭제」다.
 */
type Pending = { kind: 'preset'; preset: DashboardPreset } | { kind: 'reset' } | { kind: 'clear' };

const CONFIRM: Record<Pending['kind'], { title: string; action: string }> = {
  preset: { title: '이 구성으로 바꿀까요?', action: '바꾸기' },
  reset: { title: '기본 구성으로 초기화할까요?', action: '초기화' },
  clear: { title: '위젯을 모두 지울까요?', action: '전체 삭제' },
};

const confirmText = (pending: Pending | null, count: number): string => {
  if (pending?.kind === 'clear') return `지금 놓인 위젯 ${count}개가 모두 사라집니다.`;
  if (pending?.kind === 'reset') {
    return `지금 놓인 위젯 ${count}개를 치우고 기본 구성(위젯 ${DEFAULT_PRESET.widgets.length}개)으로 바꿉니다.`;
  }
  return `지금 놓인 위젯 ${count}개를 치우고 새 구성으로 바꿉니다.`;
};

/**
 * 대시보드를 통째로 바꾸는 동작 — 초기화(기본 구성)·전체 삭제·추천 구성 전환.
 * 화면 전체에 일어나는 일이라 사이드바가 아니라 대시보드 머리줄에 놓는다.
 */
export function DashboardApplyActions({
  dashboardId,
  projectId,
  widgets,
  onApplied,
}: {
  dashboardId: string;
  projectId: string;
  widgets: WidgetResponse[];
  onApplied: () => void;
}): ReactNode {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [presetOpen, setPresetOpen] = useState(false);

  const run = async (key: string, work: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(isApiError(e) ? e.message : '처리하지 못했습니다.');
    } finally {
      setBusy(null);
      setPending(null);
      onApplied();
    }
  };

  const confirmed = () => {
    if (!pending) return;
    if (pending.kind === 'clear') {
      void run('clear', () => clearWidgets(widgets));
      return;
    }
    const preset = pending.kind === 'reset' ? DEFAULT_PRESET : pending.preset;
    void run(pending.kind === 'reset' ? 'reset' : preset.id, () =>
      applyPreset(dashboardId, projectId, widgets, preset),
    );
  };

  return (
    <>
      {error && <span className="text-destructive text-sm">{error}</span>}
      <Button
        size="sm"
        variant="outline"
        disabled={busy !== null}
        onClick={() => setPresetOpen(true)}
      >
        {busy !== null && busy !== 'reset' && busy !== 'clear' ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <LayoutTemplate className="size-4" />
        )}
        추천 구성
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={busy !== null}
        title="기본 구성으로 되돌립니다"
        onClick={() => setPending({ kind: 'reset' })}
      >
        {busy === 'reset' ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <RotateCcw className="size-4" />
        )}
        초기화
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="text-destructive"
        disabled={widgets.length === 0 || busy !== null}
        onClick={() => setPending({ kind: 'clear' })}
      >
        {busy === 'clear' ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Trash2 className="size-4" />
        )}
        전체 삭제
      </Button>

      <Dialog open={presetOpen} onOpenChange={setPresetOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>추천 구성</DialogTitle>
            <DialogDescription>
              고르면 지금 놓인 위젯을 모두 치우고 그 구성으로 바꿉니다.
            </DialogDescription>
          </DialogHeader>

          {/* 넷을 2열 2줄로 편다 — 세로로 늘어놓으면 스크롤 없이 한눈에 안 들어온다. */}
          <div className="grid max-h-[60vh] grid-cols-2 gap-2 overflow-y-auto">
            {DASHBOARD_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                disabled={busy !== null}
                // 고른 뒤 확인을 한 번 더 받는다 — 지금 놓인 위젯이 모두 사라지는 일이다.
                onClick={() => {
                  setPresetOpen(false);
                  setPending({ kind: 'preset', preset });
                }}
                className={cn(CARD, 'w-full gap-2')}
              >
                <span className="flex w-full items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{preset.name}</span>
                  {busy === preset.id ? (
                    <Loader2 className="text-muted-foreground size-3.5 shrink-0 animate-spin" />
                  ) : (
                    <span className="text-muted-foreground text-xs font-semibold tracking-wide tnum shrink-0">
                      위젯 {preset.widgets.length}
                    </span>
                  )}
                </span>
                <span className="text-muted-foreground text-sm w-full leading-relaxed">
                  {preset.description}
                </span>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{pending && CONFIRM[pending.kind].title}</AlertDialogTitle>
            <AlertDialogDescription>{confirmText(pending, widgets.length)}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction onClick={confirmed} disabled={busy !== null}>
              {pending && CONFIRM[pending.kind].action}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/** 편집 모드의 오른쪽 자리 — 위젯 팔레트와 저장. 화면을 통째로 바꾸는 일은 머리줄이 맡는다. */
export function DashboardEditPanel({
  onPickTemplate,
  onDragTemplate,
  onClose,
  onSave,
  dirty,
  saving,
}: {
  onPickTemplate: (template: WidgetTemplate) => void;
  /** 끌기 시작·끝을 알린다 — 대시보드가 놓일 자리 상자를 그리는 데 쓴다. */
  onDragTemplate: (template: WidgetTemplate | null) => void;
  /** 편집 모드에서 나간다 — 끌던 것은 되돌린다. */
  onClose: () => void;
  /** 옮기고 늘린 자리를 저장한다. */
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
}): ReactNode {
  return (
    <div className="bg-card flex h-full flex-col overflow-hidden">
      <header className="border-border/60 flex items-center justify-between gap-2 border-b px-4 py-3">
        <p className="text-lg font-semibold tracking-tight min-w-0 truncate">편집 모드</p>
        <Button size="icon" variant="ghost" className="shrink-0" onClick={onClose}>
          <X className="size-4" />
          <span className="sr-only">편집 모드 닫기</span>
        </Button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto p-4">
        <section>
          <p className="win-label mb-2">위젯</p>
          <div className="flex flex-col gap-3">
            {[
              ...TEMPLATE_GROUPS,
              ...(UNGROUPED.length > 0 ? [{ label: '기타', items: UNGROUPED }] : []),
            ].map((group) => (
              <div key={group.label}>
                <p className="text-muted-foreground text-xs font-semibold tracking-wide mb-1.5">
                  {group.label}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {group.items.map((template) => (
                    <button
                      key={template}
                      type="button"
                      onClick={() => onPickTemplate(template)}
                      // 눌러도 되고 대시보드로 끌어다 놓아도 된다 — 둘 다 같은 창을 연다.
                      // 자리 상자는 react-grid-layout 의 isDroppable 이 그린다.
                      draggable
                      onDragStart={(e) => {
                        // 데이터가 없으면 브라우저가 끌기를 취소한다.
                        e.dataTransfer.setData('text/plain', template);
                        e.dataTransfer.effectAllowed = 'copy';
                        onDragTemplate(template);
                      }}
                      onDragEnd={() => onDragTemplate(null)}
                      className={cn(
                        CARD,
                        'items-stretch gap-2 text-center',
                        'cursor-grab active:cursor-grabbing',
                      )}
                    >
                      <WidgetSketch template={template} />
                      <span className="text-sm font-medium">{labelOf(template)}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* 저장은 손이 가장 자주 가는 자리 — 맨 아래에 붙여 둔다. */}
      <div className="border-border/60 shrink-0 border-t p-4">
        <Button className="w-full justify-center" disabled={!dirty || saving} onClick={onSave}>
          <Check className="size-4" />
          {saving ? '저장 중…' : '저장'}
        </Button>
      </div>
    </div>
  );
}
