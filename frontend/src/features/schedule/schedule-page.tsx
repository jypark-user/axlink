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
import type { CompletionItem, CompletionSummaryResponse, WbsScheduleResponse } from '@/types/api';
import { CompletionPanel } from '@/features/schedule/completion-panel';
import { RecognitionPanel } from '@/features/schedule/recognition-panel';
import { SourceFilePanel } from '@/features/schedule/source-file-panel';

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
  NONE: '일정을 읽을 WBS 파일도 Redmine 일정도 없습니다.',
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

  const completion = useAsync<CompletionSummaryResponse>(
    () => api.get<CompletionSummaryResponse>(`/projects/${project.id}/wbs/completion`),
    [project.id],
  );
  // WBS 탭의 「작업 완료 확인」 칸. 작업 번호로 잇는다
  const completionByWbs = useMemo(
    () => new Map<string, CompletionItem>((completion.data?.items ?? []).map((i) => [i.wbsId, i])),
    [completion.data],
  );

  const pick = (next: string) => {
    setView(next as ViewId);
    window.localStorage.setItem(VIEW_KEY, next);
  };

  return (
    <>
      <PageHeader title="일정(WBS)" description="용역사 WBS 기준의 작업 일정과 진척입니다." />
      <DataState state={state} onRetry={state.reload}>
        {(data) => {
          const tasks = toScheduleTasks(data.items);
          // 말단 작업만 센다. 상위 항목은 하위의 합이라 따로 세면 두 번 센다.
          const leaves = tasks.filter((t) => t.level > 0 || tasks.length === 1);
          const late = leaves.filter((t) => scheduleStatusOf(t) === 'late').length;
          const dl = data.deliverables ?? { submitted: 0, missing: 0, overdue: 0, none: 0 };
          const expected = dl.submitted + dl.missing + dl.overdue;

          const recognition = data.recognition ? (
            <RecognitionPanel recognition={data.recognition} shownLeaves={leaves.length} />
          ) : null;

          // 원천 → 두 진척 카드 → 인식 결과 → 작업 일정 순이다
          const head = (
            <>
              <SourceFilePanel data={data} />
              <CompletionPanel state={completion} />
            </>
          );

          if (data.source === 'NONE') {
            return (
              <>
                <CompletionPanel state={completion} />
                {recognition}
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
              </>
            );
          }

          return (
            <>
              {head}
              {recognition}
              <Window
                title="작업 일정"
                hint={
                  <>
                    작업 {leaves.length}개
                    {late > 0 ? (
                      <>
                        {' '}
                        · 계획보다 늦은 작업{' '}
                        <span className="tnum text-destructive font-medium">{late}</span>개
                      </>
                    ) : (
                      ' · 모두 계획대로 진행 중'
                    )}
                    {expected > 0 && (
                      <>
                        {/* 파일·문서가 있는지 대조한 결과다. 정식 제출·승인과 다르다 */} · 산출물
                        파일 대조 <span className="tnum">{dl.submitted}</span>/{expected}개
                        {dl.overdue > 0 && (
                          <>
                            , 지연{' '}
                            <span className="tnum text-destructive font-medium">{dl.overdue}</span>
                            개
                          </>
                        )}
                      </>
                    )}
                  </>
                }
                className="pt-0"
                action={<ScheduleLegend />}
                bleed
              >
                {/* 어느 파일에서 왔는지는 맨 위 「수치의 원천」이 말한다 */}
                <p className="text-muted-foreground mb-3 text-sm">
                  {SOURCE_DESCRIPTION[data.source]}
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
                    <WbsView tasks={tasks} completion={completionByWbs} />
                  </TabsContent>
                </Tabs>
              </Window>
            </>
          );
        }}
      </DataState>
    </>
  );
}
