import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Gantt, ViewMode, type Task } from 'gantt-task-react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import koLocale from '@fullcalendar/core/locales/ko';
import type { DatesSetArg, DayCellContentArg, EventContentArg } from '@fullcalendar/core';
import type { ColumnDef } from '@tanstack/react-table';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { DataTable, SortableHeader } from '@/components/ui/data-table';
import { cn } from '@/lib/utils';
import { badgeVariantFor, label as labelOf } from '@/lib/labels';
import { ServerLink } from '@/components/common/server-link';
import { useThemeColors } from '@/lib/theme-color';
import {
  DAY_MS,
  SCHEDULE_STATUS_BADGE,
  SCHEDULE_STATUS_BAR,
  SCHEDULE_STATUS_LABEL,
  SCHEDULE_STATUS_ORDER,
  dayOf,
  scheduleStatusOf,
  spanOf,
  type ScheduleStatus,
  type ScheduleTask,
} from '@/features/schedule/schedule-task';
import 'gantt-task-react/dist/index.css';
import './schedule-gantt.css';
import './schedule-calendar.css';

/** 상태 네 가지 설명. 세 보기가 같은 색을 쓰므로 한 번만 밝혀 둔다. */
export function ScheduleLegend(): ReactNode {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-2">
      {SCHEDULE_STATUS_ORDER.map((status) => (
        <li key={status} className="text-sm text-muted-foreground flex items-center gap-1.5">
          <span className={cn('size-2.5 rounded-full', SCHEDULE_STATUS_BAR[status])} aria-hidden />
          {SCHEDULE_STATUS_LABEL[status]}
        </li>
      ))}
    </ul>
  );
}

/** 막대·칩을 눌렀을 때 뜨는 설명. 간트와 캘린더가 같이 쓴다. */
function TaskCallout({ task }: { task: ScheduleTask }): ReactNode {
  const status = scheduleStatusOf(task);
  return (
    <div className="border-border bg-card shadow-win-front min-w-56 rounded-md border p-3">
      <p className="tnum text-muted-foreground text-xs font-semibold tracking-wide font-mono">
        {task.code}
      </p>
      <p className="text-sm mt-1 font-medium">{task.name}</p>
      <p className="tnum text-muted-foreground text-sm mt-2">
        {task.startAt} ~ {task.endAt}
      </p>
      <p className="tnum text-sm mt-1">
        진척 {task.progress}% · 계획 {task.planned}%
      </p>
      {status === 'late' && (
        <p className="tnum text-destructive text-xs font-semibold tracking-wide mt-1">
          {task.planned - task.progress}%p 미달
        </p>
      )}
    </div>
  );
}

/* ────────────────────────────── 간트 ────────────────────────────── */

const LIST_WIDTH = '268px';
const ROW_HEIGHT = 38;
const HEADER_HEIGHT = 52;

/** 막대 [바탕, 진척] 색. SVG 라 실제 색 문자열이 필요하다. */
const BAR_TOKENS: Record<ScheduleStatus, [string, string]> = {
  upcoming: ['var(--color-border)', 'var(--color-input)'],
  running: ['var(--color-primary-muted)', 'var(--color-primary)'],
  late: ['var(--color-destructive-muted)', 'var(--color-destructive)'],
  done: ['var(--color-success-muted)', 'var(--color-success)'],
};

export function GanttView({ tasks, today }: { tasks: ScheduleTask[]; today: number }): ReactNode {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const palette = useThemeColors([
    ...SCHEDULE_STATUS_ORDER.flatMap((status) => BAR_TOKENS[status]),
    'var(--color-primary-muted)',
  ]);

  const barColor = useMemo(() => {
    const map = {} as Record<ScheduleStatus, { background: string; progress: string }>;
    SCHEDULE_STATUS_ORDER.forEach((status, index) => {
      map[status] = { background: palette[index * 2], progress: palette[index * 2 + 1] };
    });
    return map;
  }, [palette]);

  const source = useMemo(
    () => tasks.filter((t) => !Number.isNaN(dayOf(t.startAt)) && !Number.isNaN(dayOf(t.endAt))),
    [tasks],
  );
  const detail = useMemo(() => new Map(source.map((t) => [t.id, t])), [source]);

  const ganttTasks = useMemo<Task[]>(
    () =>
      source.map((task) => {
        const colors = barColor[scheduleStatusOf(task)];
        return {
          id: task.id,
          // 전부 task 로 둔다 — project 모양은 양끝에 삼각 꼬리를 그려서 깨져 보인다.
          type: 'task',
          name: task.name,
          start: new Date(dayOf(task.startAt)),
          end: new Date(dayOf(task.endAt) + DAY_MS - 1),
          progress: task.progress,
          isDisabled: true,
          styles: {
            backgroundColor: colors.background,
            backgroundSelectedColor: colors.background,
            progressColor: colors.progress,
            progressSelectedColor: colors.progress,
          },
        } satisfies Task;
      }),
    [source, barColor],
  );

  const parts = useMemo(
    () => ({
      TooltipContent: function GanttTooltip({ task }: { task: Task }) {
        const item = detail.get(task.id);
        return item ? <TaskCallout task={item} /> : null;
      },

      TaskListHeader: function GanttListHeader({ headerHeight }: { headerHeight: number }) {
        return (
          <div
            style={{ width: LIST_WIDTH, height: headerHeight }}
            className="border-border text-muted-foreground text-xs font-semibold tracking-wide flex shrink-0 items-center gap-3 border-r border-b px-3"
          >
            <span className="w-12 shrink-0">코드</span>
            <span className="min-w-0 flex-1">활동</span>
            <span className="w-10 shrink-0 text-right">진척</span>
          </div>
        );
      },

      TaskListTable: function GanttListTable({
        rowHeight,
        tasks: rows,
      }: {
        rowHeight: number;
        tasks: Task[];
      }) {
        return (
          <div style={{ width: LIST_WIDTH }} className="border-border shrink-0 border-r">
            {rows.map((row) => {
              const item = detail.get(row.id);
              if (!item) return null;
              return (
                <div
                  key={row.id}
                  style={{ height: rowHeight }}
                  className="border-border/60 hover:bg-muted flex items-center gap-3 border-b px-3 transition-colors"
                  title={item.name}
                >
                  <span className="tnum text-muted-foreground text-xs font-semibold tracking-wide w-12 shrink-0">
                    {item.code}
                  </span>
                  <span
                    className={cn(
                      'text-sm min-w-0 flex-1 truncate',
                      item.level === 0 && 'font-semibold',
                    )}
                    style={{ paddingLeft: item.level * 10 }}
                  >
                    {item.name}
                  </span>
                  <span className="tnum text-muted-foreground text-sm w-10 shrink-0 text-right">
                    {item.progress}%
                  </span>
                </div>
              );
            })}
          </div>
        );
      },
    }),
    [detail],
  );

  // 눈금은 기간에 맞춘다 — 한 달짜리 사업을 월 단위로 그리면 막대가 한 칸에 뭉친다.
  const span = useMemo(() => spanOf(source), [source]);
  const days = span ? (span.end - span.start) / DAY_MS : 0;
  const scale =
    days <= 45
      ? { mode: ViewMode.Day, width: 32 } // 날짜 숫자만 남으므로 좁아도 붙지 않는다
      : days <= 180
        ? { mode: ViewMode.Week, width: 68 }
        : { mode: ViewMode.Month, width: 150 };

  // gantt-task-react 는 눈금 머리글을 '금, 21' 로 그리고 형식을 바꿀 길을 열어 두지 않았다.
  // 요일을 떼고 날짜만 남기려면 그린 뒤에 손대는 수밖에 없다.
  useEffect(() => {
    const root = surfaceRef.current;
    if (!root || scale.mode !== ViewMode.Day) return;

    const trim = () => {
      root.querySelectorAll<SVGTextElement>('g.calendar text').forEach((node) => {
        const matched = /^\D+,\s*(\d+)$/.exec(node.textContent ?? '');
        if (matched) node.textContent = matched[1];
      });
    };

    trim();
    // 가로로 스크롤하면 머리글을 다시 그린다 — 그때마다 따라간다.
    const observer = new MutationObserver(trim);
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [scale.mode, ganttTasks]);

  if (ganttTasks.length === 0) return null;

  // 오늘이 기간 밖이면 사업 시작에서 연다.
  const viewDate = span
    ? new Date(Math.min(Math.max(today, span.start), span.end))
    : new Date(today);

  // shadcn 표면 규칙대로 모서리를 둥글린 테두리 안에 가둔다 — 라이브러리 SVG 가 맨살로 노출되지 않게.
  return (
    <div
      ref={surfaceRef}
      className="schedule-gantt border-border min-w-0 overflow-x-auto rounded-lg border"
    >
      <Gantt
        tasks={ganttTasks}
        viewMode={scale.mode}
        viewDate={viewDate}
        locale="ko-KR"
        listCellWidth={LIST_WIDTH}
        columnWidth={scale.width}
        rowHeight={ROW_HEIGHT}
        headerHeight={HEADER_HEIGHT}
        barCornerRadius={5}
        barFill={62}
        fontFamily="inherit"
        fontSize="13px"
        todayColor={palette[palette.length - 1]}
        /* eslint-disable @typescript-eslint/unbound-method -- 객체에 담긴 React 컴포넌트지 메서드가 아니다. this 가 필요 없다. */
        TooltipContent={parts.TooltipContent}
        TaskListHeader={parts.TaskListHeader}
        TaskListTable={parts.TaskListTable}
        /* eslint-enable @typescript-eslint/unbound-method */
      />
    </div>
  );
}

/* ────────────────────────────── 칸반 ────────────────────────────── */

export function KanbanView({ tasks }: { tasks: ScheduleTask[] }): ReactNode {
  const columns = SCHEDULE_STATUS_ORDER.map((status) => ({
    status,
    items: tasks.filter((task) => scheduleStatusOf(task) === status),
  }));

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {columns.map((column) => (
        // 열마다 옅은 바탕을 깔아 레인을 세운다 — 카드가 허공에 떠 있으면 열 경계가 안 보인다.
        <section key={column.status} className="bg-muted/40 flex min-w-0 flex-col rounded-lg p-2">
          <header className="flex items-center gap-2 px-1 pb-2">
            <Badge variant={SCHEDULE_STATUS_BADGE[column.status]}>
              {SCHEDULE_STATUS_LABEL[column.status]}
            </Badge>
            <span className="tnum text-muted-foreground text-sm ml-auto">
              {column.items.length}
            </span>
          </header>

          {column.items.length === 0 ? (
            <p className="border-border text-muted-foreground text-sm flex min-h-40 items-center justify-center rounded-lg border border-dashed px-3 text-center">
              해당 작업 없음
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {column.items.map((task) => (
                <li key={task.id}>
                  <Card className="hover:border-input gap-1 rounded-lg p-3 shadow-none transition-colors">
                    <p className="tnum text-muted-foreground text-xs font-semibold tracking-wide truncate font-mono">
                      {task.code}
                    </p>
                    <p className="text-sm truncate font-medium">{task.name}</p>
                    <p className="tnum text-muted-foreground text-sm truncate">
                      {task.startAt} ~ {task.endAt}
                    </p>

                    <div className="mt-2 flex items-center gap-2">
                      <span className="bg-accent h-1.5 min-w-0 flex-1 overflow-hidden rounded-full">
                        <span
                          className={cn(
                            'block h-full rounded-full',
                            SCHEDULE_STATUS_BAR[column.status],
                          )}
                          style={{ width: `${task.progress}%` }}
                        />
                      </span>
                      <span className="tnum text-sm font-medium">{task.progress}%</span>
                    </div>

                    {column.status === 'late' && (
                      <p className="text-xs font-semibold tracking-wide tnum text-destructive truncate">
                        계획 {task.planned}% 대비 {task.planned - task.progress}%p 미달
                      </p>
                    )}
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}

/* ────────────────────────────── WBS ────────────────────────────── */

/** 작업분해구조. 묶음과 활동을 들여쓰기로 세우고 계획 대비 진척을 나란히 놓는다. */
const DELIVERABLE_LABEL: Record<ScheduleTask['deliverableStatus'], string> = {
  NONE: '',
  SUBMITTED: '제출',
  MISSING: '미제출',
  OVERDUE: '지연',
};

const DELIVERABLE_TONE: Record<ScheduleTask['deliverableStatus'], string> = {
  NONE: '',
  SUBMITTED: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  MISSING: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  OVERDUE: 'bg-destructive/15 text-destructive',
};

/** 산출물 칸. 판정 결과를 알약으로, 근거(맞춘 파일)는 제목에, 링크가 있으면 원문으로. */
/**
 * 작업에 이어진 이슈와 그 최근 상태(AC-041-4). 서버가 이은 그대로 적고, 상태는 이슈 화면과 같은
 * 말(열림·진행중·해결·종료)로 쓴다. 원문 주소가 있으면 원천의 그 이슈로 간다.
 */
function LinkedIssuesCell({ task }: { task: ScheduleTask }): ReactNode {
  if (task.linkedIssues.length === 0) return <span className="text-muted-foreground text-sm">—</span>;
  return (
    <span className="flex flex-col gap-1">
      {task.linkedIssues.map((issue, i) => {
        const key = issue.key ?? issue.title;
        return (
          <span key={`${key}-${i}`} className="flex items-center gap-1.5 text-xs" title={issue.title}>
            {issue.url ? (
              <a
                href={issue.url}
                target="_blank"
                rel="noreferrer"
                className="text-primary font-mono whitespace-nowrap underline-offset-2 hover:underline"
              >
                {key}
              </a>
            ) : (
              <span className="font-mono whitespace-nowrap">{key}</span>
            )}
            <Badge variant={badgeVariantFor(issue.status)}>{labelOf(issue.status)}</Badge>
          </span>
        );
      })}
    </span>
  );
}

function DeliverableCell({ task }: { task: ScheduleTask }): ReactNode {
  if (!task.deliverable) return <span className="text-muted-foreground text-sm">—</span>;
  const label = DELIVERABLE_LABEL[task.deliverableStatus];
  const title = task.deliverableRef
    ? `${task.deliverable} · ${task.deliverableRef}`
    : task.deliverable;
  const pill = (
    <span
      className={cn(
        'inline-block rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
        DELIVERABLE_TONE[task.deliverableStatus],
      )}
      title={title}
    >
      {label}
    </span>
  );
  return (
    <span className="flex items-center gap-2">
      {task.deliverableUrl ? (
        <ServerLink
          url={task.deliverableUrl}
          filename={task.deliverable ?? 'deliverable'}
          className="underline-offset-2 hover:underline"
        >
          {pill}
        </ServerLink>
      ) : (
        pill
      )}
      <span
        className="text-muted-foreground block max-w-[14rem] truncate text-xs"
        title={task.deliverable}
      >
        {task.deliverable}
      </span>
      {task.gapWarning && (
        <span
          className="inline-block rounded bg-amber-500/15 px-1.5 py-0.5 text-xs font-medium whitespace-nowrap text-amber-700 dark:text-amber-300"
          title={task.gapWarning}
        >
          격차 경고
        </span>
      )}
    </span>
  );
}

export function WbsView({ tasks }: { tasks: ScheduleTask[] }): ReactNode {
  const columns = useMemo<ColumnDef<ScheduleTask, unknown>[]>(
    () => [
      {
        accessorKey: 'code',
        header: '번호',
        cell: ({ row }) => (
          <span className="tnum text-muted-foreground text-sm font-mono">{row.original.code}</span>
        ),
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <SortableHeader column={column}>작업</SortableHeader>,
        cell: ({ row }) => (
          <span
            className={cn('text-sm block truncate', row.original.level === 0 && 'font-semibold')}
            style={{ paddingLeft: row.original.level * 16 }}
            title={row.original.name}
          >
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'period',
        accessorFn: (task) => task.startAt,
        header: ({ column }) => <SortableHeader column={column}>기간</SortableHeader>,
        cell: ({ row }) => (
          <span className="tnum text-muted-foreground text-sm whitespace-nowrap">
            {row.original.startAt} ~ {row.original.endAt}
          </span>
        ),
      },
      {
        accessorKey: 'owner',
        header: '범위',
        cell: ({ row }) => (
          <span className="text-muted-foreground text-sm">{row.original.owner}</span>
        ),
      },
      {
        id: 'deliverable',
        accessorFn: (task) => task.deliverableStatus,
        header: '산출물',
        cell: ({ row }) => <DeliverableCell task={row.original} />,
      },
      {
        id: 'linkedIssues',
        header: '연결 이슈',
        cell: ({ row }) => <LinkedIssuesCell task={row.original} />,
      },
      {
        accessorKey: 'planned',
        header: ({ column }) => <SortableHeader column={column}>계획</SortableHeader>,
        cell: ({ row }) => <span className="tnum text-sm">{row.original.planned}%</span>,
      },
      {
        accessorKey: 'progress',
        header: ({ column }) => <SortableHeader column={column}>진척</SortableHeader>,
        cell: ({ row }) => {
          const task = row.original;
          const behind = task.progress < task.planned;
          return (
            <span className="flex items-center justify-end gap-3">
              {/* 계획선을 같이 그어 두면 얼마나 벌어졌는지 눈으로 바로 읽힌다. */}
              <span className="bg-accent relative h-1.5 w-24 shrink-0 overflow-hidden rounded-full">
                <span
                  className={cn(
                    'block h-full rounded-full',
                    SCHEDULE_STATUS_BAR[scheduleStatusOf(task)],
                  )}
                  style={{ width: `${task.progress}%` }}
                />
                <span
                  aria-hidden
                  className="bg-muted-foreground/50 absolute top-0 h-full w-px"
                  style={{ left: `${task.planned}%` }}
                />
              </span>
              <span
                className={cn(
                  'tnum text-sm w-10 text-right font-medium',
                  behind && 'text-destructive',
                )}
              >
                {task.progress}%
              </span>
            </span>
          );
        },
      },
    ],
    [],
  );

  return (
    <DataTable<ScheduleTask, unknown>
      columns={columns}
      data={tasks}
      filterColumn="name"
      filterPlaceholder="작업 이름으로 찾기"
      paginated={false}
      emptyText="작업이 없습니다."
    />
  );
}

/* ───────────────────────────── 캘린더 ───────────────────────────── */

const monthKey = (year: number, month: number) => year * 12 + month;

export function CalendarView({
  tasks,
  today,
}: {
  tasks: ScheduleTask[];
  today: number;
}): ReactNode {
  const calendarRef = useRef<FullCalendar>(null);
  const initial = new Date(today);
  const [cursor, setCursor] = useState(() => monthKey(initial.getFullYear(), initial.getMonth()));

  const span = useMemo(() => spanOf(tasks), [tasks]);

  const bounds = useMemo(() => {
    if (!span) return null;
    const from = new Date(span.start);
    const to = new Date(span.end);
    return {
      min: monthKey(from.getFullYear(), from.getMonth()),
      max: monthKey(to.getFullYear(), to.getMonth()),
    };
  }, [span]);

  // 묶음 머리줄은 사업 기간 전체라 달력을 덮어버린다 — 활동만 올린다.
  const events = useMemo(
    () =>
      tasks
        .filter(
          (t) => t.level > 0 && !Number.isNaN(dayOf(t.startAt)) && !Number.isNaN(dayOf(t.endAt)),
        )
        .map((task) => ({
          id: task.id,
          title: task.name,
          start: task.startAt,
          end: new Date(dayOf(task.endAt) + DAY_MS),
          allDay: true,
          extendedProps: { task },
        })),
    [tasks],
  );

  const api = () => calendarRef.current?.getApi();
  const year = Math.floor(cursor / 12);
  const month = cursor % 12;

  const renderDayCell = (arg: DayCellContentArg) => (
    <span
      className={cn(
        'tnum text-xs font-semibold tracking-wide flex size-6 items-center justify-center rounded-full',
        arg.isToday
          ? 'bg-primary text-primary-foreground font-semibold'
          : arg.isOther
            ? 'text-muted-foreground/40'
            : 'text-foreground',
      )}
    >
      {arg.dayNumberText.replace('일', '')}
    </span>
  );

  const renderEvent = (arg: EventContentArg) => {
    const task = arg.event.extendedProps.task as ScheduleTask;
    return (
      <Badge
        variant={SCHEDULE_STATUS_BADGE[scheduleStatusOf(task)]}
        title={`${task.name} · 진척 ${task.progress}% (계획 ${task.planned}%)`}
        className="flex w-full justify-start rounded-sm font-normal"
      >
        <span className="min-w-0 flex-1 truncate">{task.name}</span>
        {/* 띠 하나에 이름만 있으면 다음 주로 이어질 때 같은 말만 반복된다. 진척을 같이 얹는다. */}
        <span className="tnum shrink-0 opacity-70">{task.progress}%</span>
      </Badge>
    );
  };

  const onDatesSet = (arg: DatesSetArg) => {
    const current = arg.view.currentStart;
    setCursor(monthKey(current.getFullYear(), current.getMonth()));
  };

  return (
    <div className="schedule-calendar min-w-0">
      {/* 달 표시는 왼쪽에 두고 조작은 오른쪽에 모은다 — 버튼 사이에 글이 끼면 읽는 순서가 끊긴다. */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3">
        <p className="tnum text-lg font-semibold tracking-tight">
          {year}년 {month + 1}월
        </p>

        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => api()?.today()}>
            오늘
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="이전 달"
            disabled={bounds ? cursor <= bounds.min : false}
            onClick={() => api()?.prev()}
          >
            <span className="sr-only">이전 달</span>
            <ChevronLeft />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="다음 달"
            disabled={bounds ? cursor >= bounds.max : false}
            onClick={() => api()?.next()}
          >
            <span className="sr-only">다음 달</span>
            <ChevronRight />
          </Button>
        </div>
      </div>

      {/* 달력도 같은 표면 규칙 — 둥근 테두리 안에 격자를 가둔다. */}
      <div className="border-border overflow-hidden rounded-lg border">
        <FullCalendar
          ref={calendarRef}
          plugins={[dayGridPlugin]}
          initialView="dayGridMonth"
          initialDate={new Date(today)}
          locale={koLocale}
          headerToolbar={false}
          height="auto"
          fixedWeekCount={false}
          dayMaxEvents={3}
          events={events}
          dayCellContent={renderDayCell}
          eventContent={renderEvent}
          datesSet={onDatesSet}
        />
      </div>
    </div>
  );
}
