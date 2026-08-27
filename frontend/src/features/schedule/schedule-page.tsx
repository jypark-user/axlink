import { useMemo, useState, type ReactNode } from 'react';
import { CalendarDays, ChartGantt, LayoutGrid, ListTree } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Window } from '@/components/ui/window';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { useAsync } from '@/lib/use-async';
import { buildActivityTasks } from '@/features/schedule/activity-schedule';
import { scheduleStatusOf } from '@/features/schedule/schedule-task';
import {
  CalendarView,
  GanttView,
  KanbanView,
  ScheduleLegend,
  WbsView,
} from '@/features/schedule/schedule-views';
import type { WorkProductChecklistResponse } from '@/types/api';

const VIEW_KEY = 'ax-link.schedule-view';

const VIEWS = [
  { id: 'gantt', label: '간트', icon: ChartGantt },
  { id: 'kanban', label: '칸반', icon: LayoutGrid },
  { id: 'calendar', label: '캘린더', icon: CalendarDays },
  { id: 'wbs', label: 'WBS', icon: ListTree },
] as const;

type ViewId = (typeof VIEWS)[number]['id'];

function readView(): ViewId {
  if (typeof window === 'undefined') return 'gantt';
  const saved = window.localStorage.getItem(VIEW_KEY);
  return VIEWS.some((v) => v.id === saved) ? (saved as ViewId) : 'gantt';
}

export function SchedulePage(): ReactNode {
  const { project } = useProjectContext();
  const [view, setView] = useState<ViewId>(readView);
  // 한 번 고정한다 — 그리는 중에 값이 바뀌면 막대와 오늘 선이 흔들린다.
  const today = useMemo(() => Date.now(), []);

  const state = useAsync<WorkProductChecklistResponse>(
    () => api.get<WorkProductChecklistResponse>(`/projects/${project.id}/work-products`),
    [project.id],
  );

  const pick = (next: string) => {
    setView(next as ViewId);
    window.localStorage.setItem(VIEW_KEY, next);
  };

  return (
    <>
      <PageHeader
        title="일정"
        description="ISO/IEC 29110 활동별 진척입니다. 진척은 그 활동에 걸린 산출물의 승인 비율입니다."
      />

      <DataState state={state} onRetry={state.reload}>
        {(data) => {
          const { tasks, datesAreEstimated } = buildActivityTasks(
            data.items,
            project.startDate,
            project.endDate,
            today,
          );
          const activities = tasks.filter((t) => t.level > 0);
          const late = activities.filter((t) => scheduleStatusOf(t) === 'late').length;

          return (
            <Window
              title="활동 일정"
              hint={
                late > 0 ? (
                  <>
                    활동 {activities.length}개 · 계획보다 늦은 활동{' '}
                    <span className="tnum text-destructive font-medium">{late}</span>개
                  </>
                ) : (
                  `활동 ${activities.length}개 · 모두 계획대로 진행 중입니다`
                )
              }
              className="pt-0"
              action={<ScheduleLegend />}
              bleed
            >
              {datesAreEstimated && (
                <Alert className="mb-4">
                  <AlertDescription>
                    활동별 시작일·종료일은 아직 수집하지 않아 사업 기간을 활동 수로 나눈
                    추정치입니다. 진척률은 실제 산출물 승인 현황입니다.
                  </AlertDescription>
                </Alert>
              )}

              <Tabs value={view} onValueChange={pick}>
                <TabsList aria-label="일정 보기 방식">
                  {VIEWS.map((item) => (
                    <TabsTrigger key={item.id} value={item.id}>
                      <item.icon />
                      {item.label}
                    </TabsTrigger>
                  ))}
                </TabsList>

                <TabsContent value="gantt" className="pt-2">
                  <GanttView tasks={tasks} today={today} />
                </TabsContent>
                <TabsContent value="kanban" className="pt-2">
                  <KanbanView tasks={activities} />
                </TabsContent>
                <TabsContent value="calendar" className="pt-2">
                  <CalendarView tasks={tasks} today={today} />
                </TabsContent>
                <TabsContent value="wbs" className="pt-2">
                  <WbsView tasks={tasks} />
                </TabsContent>
              </Tabs>
            </Window>
          );
        }}
      </DataState>
    </>
  );
}
