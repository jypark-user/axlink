import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Link, useParams } from 'react-router-dom';
import { Responsive, WidthProvider, type Layouts } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { LayoutTemplate, Loader2, Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { DataState, EmptyState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { RESOURCE_DOCK_ID } from '@/components/layout/app-shell';
import { useOptionalProject } from '@/components/layout/project-shell';
import { useToast } from '@/components/common/toaster';
import { api } from '@/lib/http';
import { cn } from '@/lib/utils';
import { isApiError } from '@/lib/api-error';
import { toQueryString } from '@/lib/query';
import { useAsync } from '@/lib/use-async';
import {
  DEFAULT_SIZE,
  fillMissing,
  toDashboardLayout,
  toGridLayouts,
} from '@/features/dashboard/layout-mapper';
import { WidgetHost } from '@/features/widgets/widget-host';
import { WidgetCreateDialog } from '@/features/dashboard/widget-create-dialog';
import { DashboardApplyActions, DashboardEditPanel } from '@/features/dashboard/edit-panel';
import { DEFAULT_PRESET } from '@/features/dashboard/dashboard-presets';
import { applyPreset } from '@/features/dashboard/preset-apply';
import { ResourceSheet } from '@/features/ax-query/resource-sheet';
import type {
  DashboardDetailResponse,
  DashboardLayout,
  DashboardSummaryResponse,
  WidgetResponse,
  WidgetTemplate,
} from '@/types/api';

const ResponsiveGridLayout = WidthProvider(Responsive);

// 어느 폭에서나 12칸을 쓴다 — 칸 수가 줄면 6칸짜리 위젯이 화면을 통째로 먹는다.
const COLS = { lg: 12, md: 12, sm: 12 };

const BREAKPOINTS = { lg: 1200, md: 996, sm: 0 };

/** 끌고 오는 템플릿의 기본 크기로 놓일 자리 상자를 잡는다. */
const droppingItem = (template: WidgetTemplate | null) => {
  const size = DEFAULT_SIZE[template ?? 'STAT_CARD'];
  return { i: '__dropping__', w: size.w, h: size.h };
};
/** 칸 높이·여백. */
const ROW_HEIGHT = 80;
const MARGIN = 16;

async function resolveDashboardId(
  dashboardId: string | undefined,
  projectId: string | undefined,
): Promise<string | null> {
  if (dashboardId) return dashboardId;
  const list = await api.get<DashboardSummaryResponse[]>(
    `/dashboards${toQueryString({ projectId: projectId ?? null })}`,
  );
  const preferred = list.find((d) => d.isDefault) ?? list[0];
  return preferred?.id ?? null;
}

export function DashboardPage(): ReactNode {
  const { dashboardId, projectId } = useParams();
  const { toast } = useToast();
  // 미처리 확인 요청 건수는 현황 화면에도 보인다 (SWFR.WEB.006). 사업 밖 대시보드에는 없다
  const project = useOptionalProject();

  const state = useAsync<DashboardDetailResponse | null>(async () => {
    const id = await resolveDashboardId(dashboardId, projectId);
    if (!id) return null;
    return api.get<DashboardDetailResponse>(`/dashboards/${id}`);
  }, [dashboardId, projectId]);

  const dashboard = state.data;

  const [editing, setEditing] = useState(false);
  /** 사이드바에서 고른 위젯 자리 — 값이 있으면 그 형태로 모달이 열린다. */
  const [picked, setPicked] = useState<WidgetTemplate | null>(null);
  // 고치는 중인 위젯 — 같은 모달을 새로 만들 때와 고칠 때 함께 쓴다.
  const [editingWidget, setEditingWidget] = useState<WidgetResponse | null>(null);
  // 사이드바에서 끌고 오는 중인 템플릿 — 놓일 자리 상자의 크기를 정한다.
  const [dragging, setDragging] = useState<WidgetTemplate | null>(null);
  const [draft, setDraft] = useState<DashboardLayout | null>(null);
  const [saving, setSaving] = useState(false);
  /** 편집 사이드바가 들어갈 자리 — 앱 셸 오른쪽 칸이라 화면 높이를 다 쓰고 머리줄까지 민다. */
  const [dock, setDock] = useState<HTMLElement | null>(null);

  useEffect(() => setDock(document.getElementById(RESOURCE_DOCK_ID)), []);

  useEffect(() => {
    setEditing(false);
    setDraft(null);
    setPicked(null);
  }, [dashboard?.id]);

  const layout = draft ?? dashboard?.layout ?? { lg: [], md: [], sm: [] };
  // 자리가 없는 위젯이 있으면 여기서 채워 넘긴다 — 라이브러리가 1x1 로 떨어뜨리지 않도록.
  const gridLayouts = useMemo(
    () =>
      toGridLayouts(
        fillMissing(
          layout,
          (dashboard?.widgets ?? []).map((w) => ({
            id: w.id,
            template: w.spec?.template ?? w.template,
          })),
        ),
      ),
    [layout, dashboard?.widgets],
  );
  const dirty = draft !== null;

  useEffect(() => {
    if (!dirty || !editing) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty, editing]);

  const onLayoutChange = useCallback(
    (_current: unknown, all: Layouts) => {
      if (!editing) return;
      setDraft(toDashboardLayout(all));
    },
    [editing],
  );

  const save = async () => {
    if (!dashboard || draft === null) return;
    setSaving(true);
    try {
      const next = await api.put<DashboardDetailResponse>(`/dashboards/${dashboard.id}/layout`, {
        layout: draft,
      });
      state.setData(next);
      setDraft(null);
      setEditing(false);
      toast({ title: '레이아웃을 저장했습니다.', variant: 'success' });
    } catch (e) {
      toast({
        title: '저장에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  /**
   * 위젯 구성이 서버에서 통째로 바뀌었다(추천 구성·초기화·개별 추가). 끌던 초안은 옛 위젯
   * id 를 물고 있어서, 그대로 두면 md 폭(편집 패널이 열려 본문이 1200px 아래로 좁아진 상태)
   * 에서 새 위젯들이 초안 레이아웃에 없다는 이유로 전부 1x1 로 떨어진다. 초안을 버리고 새로 받는다.
   */
  const applied = () => {
    setDraft(null);
    state.reload();
  };

  // 빈 화면에서 기본 구성을 바로 놓는다. 새 사업은 대시보드가 비어 있다(11-18 사용자 지시)
  const [seeding, setSeeding] = useState(false);
  const seedDefault = async (dashboardId: string) => {
    if (!projectId) return;
    setSeeding(true);
    try {
      await applyPreset(dashboardId, projectId, [], DEFAULT_PRESET);
    } catch (e) {
      toast({
        title: '기본 구성을 놓지 못했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    } finally {
      setSeeding(false);
      applied();
    }
  };

  const removeWidget = async (widgetId: string) => {
    try {
      await api.del<void>(`/widgets/${widgetId}`);
      // 서버가 자리까지 빼 주므로, 끌던 초안은 버리고 새 배치를 그대로 받는다.
      setDraft(null);
      state.reload();
    } catch (e) {
      toast({
        title: '위젯 삭제에 실패했습니다.',
        description: isApiError(e) ? e.message : undefined,
        variant: 'error',
      });
    }
  };

  return (
    <>
      <PageHeader
        title="대시보드"
        description={
          project ? (
            <>
              {dashboard?.name}
              {dashboard?.name && ' · '}
              <Link
                to={`/p/${project.id}/reviews`}
                className={cn(
                  'underline-offset-2 hover:underline',
                  project.openReviewRequestCount > 0 ? 'text-primary font-medium' : undefined,
                )}
                data-testid="open-review-count"
              >
                미처리 확인 요청 {project.openReviewRequestCount}건
              </Link>
            </>
          ) : (
            dashboard?.name
          )
        }
        actions={
          dashboard?.editable ? (
            editing && projectId ? (
              // 화면을 통째로 바꾸는 동작은 사이드바가 아니라 대시보드 머리줄에 둔다.
              <DashboardApplyActions
                dashboardId={dashboard.id}
                projectId={projectId}
                widgets={dashboard.widgets}
                onApplied={applied}
              />
            ) : (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                <Pencil className="size-4" />
                편집 모드
              </Button>
            )
          ) : null
        }
      />
      <div className="pb-8">
        <DataState
          state={state}
          onRetry={state.reload}
          skeleton={<Skeleton className="h-64 w-full" />}
          empty={{ text: '이 프로젝트에 연결된 대시보드가 없습니다.' }}
        >
          {(d) =>
            d.widgets.length === 0 ? (
              <EmptyState
                text="위젯이 없습니다. 기본 구성을 놓거나, 편집 모드에서 추천 구성을 고르거나 위젯을 하나씩 더하세요."
                action={
                  d.editable && !editing ? (
                    <div className="flex gap-2">
                      {projectId && (
                        <Button size="sm" disabled={seeding} onClick={() => void seedDefault(d.id)}>
                          {seeding ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <LayoutTemplate className="size-4" />
                          )}
                          기본 구성 놓기
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                        <Pencil className="size-4" />
                        편집 모드
                      </Button>
                    </div>
                  ) : undefined
                }
              />
            ) : (
              <div
                className={cn(
                  'relative rounded-xl transition-colors',
                  // 안내선 대신 판 전체를 편집판으로 보이게 한다 — 칸을 칠하지 않고 경계만 말한다.
                  editing && 'border-primary/30 bg-primary/[0.02] border border-dashed p-3',
                )}
              >
                <ResponsiveGridLayout
                  className="layout"
                  layouts={gridLayouts}
                  cols={COLS}
                  breakpoints={BREAKPOINTS}
                  rowHeight={ROW_HEIGHT}
                  margin={[MARGIN, MARGIN]}
                  containerPadding={[0, 0]}
                  isDraggable={editing}
                  isResizable={editing}
                  // 사이드바에서 끌고 오는 동안 놓일 자리를 상자로 보여 준다.
                  isDroppable={editing && dragging !== null}
                  droppingItem={droppingItem(dragging)}
                  onDrop={() => {
                    if (dragging) setPicked(dragging);
                    setDragging(null);
                  }}
                  // 카드 아무 데나 잡아 끈다 — 버튼·링크·입력과 크기 손잡이만 뺀다.
                  draggableCancel=".widget-no-drag, button, a, input, textarea, select, .react-resizable-handle"
                  resizeHandles={['nw', 'ne', 'sw', 'se']}
                  onLayoutChange={onLayoutChange}
                >
                  {d.widgets.map((w) => (
                    <div key={w.id}>
                      <WidgetHost
                        widget={w}
                        editing={editing}
                        onDelete={removeWidget}
                        onEdit={setEditingWidget}
                      />
                    </div>
                  ))}
                </ResponsiveGridLayout>
              </div>
            )
          }
        </DataState>
      </div>

      {editing &&
        dock &&
        dashboard &&
        projectId &&
        createPortal(
          <ResourceSheet label="대시보드 편집" resizable={false} fixedWidth={340}>
            <DashboardEditPanel
              onPickTemplate={setPicked}
              onDragTemplate={setDragging}
              onClose={() => {
                setDraft(null);
                setEditing(false);
              }}
              onSave={save}
              dirty={dirty}
              saving={saving}
            />
          </ResourceSheet>,
          dock,
        )}
      {(picked || editingWidget) && state.data && projectId && (
        <WidgetCreateDialog
          dashboardId={state.data.id}
          projectId={projectId}
          initialTemplate={picked}
          editing={editingWidget}
          existing={layout.lg ?? []}
          onClose={() => {
            setPicked(null);
            setEditingWidget(null);
          }}
          onCreated={applied}
        />
      )}
    </>
  );
}
