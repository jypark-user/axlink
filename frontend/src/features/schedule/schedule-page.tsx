import { useMemo, useState, type ReactNode } from 'react';
import { CalendarDays, ChartGantt, LayoutGrid, ListTree } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Window } from '@/components/ui/window';
import { DataState } from '@/components/common/data-state';
import { PageHeader } from '@/components/layout/page-header';
import { useProjectContext } from '@/components/layout/project-shell';
import { api } from '@/lib/http';
import { useAsync } from '@/lib/use-async';
import { scheduleStatusOf } from '@/features/schedule/schedule-task';
import {
  CalendarView,
  GanttView,
  KanbanView,
  ScheduleLegend,
  WbsView,
} from '@/features/schedule/schedule-views';
import { toScheduleTasks } from '@/features/schedule/wbs-tasks';
import type { WbsScheduleResponse } from '@/types/api';

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

const SOURCE_DESCRIPTION: Record<WbsScheduleResponse['source'], string> = {
  WBS_FILE: '용역사가 제출한 WBS 의 항목·기간·실적입니다. 계획선은 기간으로 다시 계산했습니다.',
  REDMINE: 'Redmine 이슈의 시작일·종료일·진척률입니다. WBS 파일이 없어 이것으로 대신합니다.',
  NONE: '일정의 원천이 없습니다.',
};

export function SchedulePage(): ReactNode {
  const { project } = useProjectContext();
  const [view, setView] = useState<ViewId>(readView);
  // 한 번 고정한다 — 그리는 중에 값이 바뀌면 막대와 오늘 선이 흔들린다.
  const today = useMemo(() => Date.now(), []);

  const state = useAsync<WbsScheduleResponse>(
    () => api.get<WbsScheduleResponse>(`/projects/${project.id}/wbs`),
    [project.id],
  );

  const pick = (next: string) => {
    setView(next as ViewId);
    window.localStorage.setItem(VIEW_KEY, next);
  };

  return (
    <>
      <PageHeader title="일정" description="용역사 WBS 기준의 작업 일정과 진척입니다." />

      <DataState state={state} onRetry={state.reload}>
        {(data) => {
          const tasks = toScheduleTasks(data.items);
          // 말단 작업만 센다. 상위 항목은 하위의 합이라 따로 세면 두 번 센다.
          const leaves = tasks.filter((t) => t.level > 0 || tasks.length === 1);
          const late = leaves.filter((t) => scheduleStatusOf(t) === 'late').length;

          if (data.source === 'NONE') {
            return (
              <Window title="작업 일정" className="pt-0" bleed>
                <Alert variant="destructive" className="mb-4">
                  <AlertTitle>진척률 산정의 핵심 입력이 빠져 있습니다</AlertTitle>
                  <AlertDescription>{data.notice}</AlertDescription>
                </Alert>
                {data.warnings.map((w) => (
                  <Alert key={w} className="mb-2">
                    <AlertDescription>{w}</AlertDescription>
                  </Alert>
                ))}
              </Window>
            );
          }

          return (
            <Window
              title="작업 일정"
              hint={
                late > 0 ? (
                  <>
                    작업 {leaves.length}개 · 계획보다 늦은 작업{' '}
                    <span className="tnum text-destructive font-medium">{late}</span>개
                  </>
                ) : (
                  `작업 ${leaves.length}개 · 모두 계획대로 진행 중입니다`
                )
              }
              className="pt-0"
              action={<ScheduleLegend />}
              bleed
            >
              <p className="text-muted-foreground mb-3 text-sm">
                {SOURCE_DESCRIPTION[data.source]}{' '}
                {data.sourceUrl ? (
                  <a
                    href={data.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary underline-offset-2 hover:underline"
                  >
                    {data.sourceLabel}
                  </a>
                ) : (
                  <span>{data.sourceLabel}</span>
                )}
                {data.planVersion && <span className="tnum"> · 버전 {data.planVersion}</span>}
                <span className="tnum"> · 기준일 {data.baseDate}</span>
              </p>

              {data.warnings.map((w) => (
                <Alert key={w} className="mb-2">
                  <AlertDescription>{w}</AlertDescription>
                </Alert>
              ))}

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
                  <KanbanView tasks={leaves} />
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
