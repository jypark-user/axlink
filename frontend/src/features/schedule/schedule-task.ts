/**
 * 일정 화면이 쓰는 작업 한 줄. 모양은 ax-pms ScheduleTask 를 그대로 따른다.
 * 날짜는 `YYYY-MM-DD`(예: `2026-03-02`), 진척은 0~100 정수다.
 */
export interface ScheduleTask {
  id: string;
  code: string;
  /** 들여쓰기 깊이. 0 이 최상위. */
  level: number;
  name: string;
  owner: string;
  startAt: string;
  endAt: string;
  /** 실제 진척률. */
  progress: number;
  /** 오늘 기준 계획 진척률. progress 가 이보다 낮으면 늦은 것이다. */
  planned: number;
  /** WBS 가 정한 산출물과 그 제출 판정. 묶음은 NONE */
  deliverable: string | null;
  deliverableStatus: DeliverableStatus;
  deliverableRef: string | null;
  deliverableUrl: string | null;
  /** 작업 단위 격차 경고(DEC-20). 서버가 판정한 문장 그대로다 */
  gapWarning: string | null;
}

export type DeliverableStatus = 'NONE' | 'SUBMITTED' | 'MISSING' | 'OVERDUE';

export type ScheduleStatus = 'upcoming' | 'running' | 'late' | 'done';

export const SCHEDULE_STATUS_ORDER: ScheduleStatus[] = ['upcoming', 'running', 'late', 'done'];

export const SCHEDULE_STATUS_LABEL: Record<ScheduleStatus, string> = {
  upcoming: '시작 전',
  running: '진행 중',
  late: '계획보다 늦음',
  done: '완료',
};

/** 상태 딱지 */
export const SCHEDULE_STATUS_TONE: Record<ScheduleStatus, string> = {
  upcoming: 'bg-accent text-muted-foreground',
  running: 'bg-primary-muted text-primary',
  late: 'bg-destructive-muted text-destructive',
  done: 'bg-success-muted text-success',
};

/** 상태를 shadcn Badge 로 보여줄 때의 variant — 톤 표와 같은 색 체계다. */
export const SCHEDULE_STATUS_BADGE: Record<
  ScheduleStatus,
  'muted' | 'primary' | 'destructive' | 'success'
> = {
  upcoming: 'muted',
  running: 'primary',
  late: 'destructive',
  done: 'success',
};

/** 막대 채움 */
export const SCHEDULE_STATUS_BAR: Record<ScheduleStatus, string> = {
  upcoming: 'bg-input',
  running: 'bg-primary',
  late: 'bg-destructive',
  done: 'bg-success',
};

/** 막대 바탕 */
export const SCHEDULE_STATUS_TRACK: Record<ScheduleStatus, string> = {
  upcoming: 'bg-secondary',
  running: 'bg-primary-muted',
  late: 'bg-destructive-muted',
  done: 'bg-success-muted',
};

export function scheduleStatusOf(task: ScheduleTask): ScheduleStatus {
  if (task.progress >= 100) return 'done';
  if (task.progress < task.planned) return 'late';
  if (task.progress > 0) return 'running';
  return 'upcoming';
}

export const DAY_MS = 86_400_000;

export const dayOf = (value: string): number => Date.parse(`${value}T00:00:00`);

/** 작업 전체가 걸쳐 있는 기간. 날짜를 하나도 못 읽으면 null. */
export function spanOf(tasks: ScheduleTask[]): { start: number; end: number } | null {
  const starts = tasks.map((t) => dayOf(t.startAt)).filter((v) => !Number.isNaN(v));
  const ends = tasks.map((t) => dayOf(t.endAt)).filter((v) => !Number.isNaN(v));
  if (starts.length === 0 || ends.length === 0) return null;
  return { start: Math.min(...starts), end: Math.max(...ends) };
}
