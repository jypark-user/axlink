import { DAY_MS, dayOf, type ScheduleTask } from '@/features/schedule/schedule-task';
import type { WorkProductResponse } from '@/types/api';

/**
 * ax-link 에는 아직 작업(WBS) 표가 없다. 그래서 ISO/IEC 29110 활동을 작업 한 줄로 삼고,
 * 진척은 그 활동에 걸린 산출물의 승인 비율로 잡는다 — 이미 있는 점검표 데이터다.
 *
 * 다만 활동별 시작일·종료일은 어디에도 없어서 사업 기간을 활동 수로 나눈 **추정치**다.
 * 실제 일정을 수집하기 시작하면 이 파일을 걷어내고 서버가 준 작업을 그대로 쓰면 된다.
 */

const PM_ACTIVITY_NAME: Record<string, string> = {
  PM_1: 'PM.1 사업 착수 · 계획',
  PM_2: 'PM.2 사업 수행 · 관리',
  PM_3: 'PM.3 사업 평가 · 시정',
  PM_4: 'PM.4 사업 종료 · 인도',
};

const SI_ACTIVITY_NAME: Record<string, string> = {
  SI_1: 'SI.1 착수',
  SI_2: 'SI.2 요구사항 분석',
  SI_3: 'SI.3 설계',
  SI_4: 'SI.4 구현',
  SI_5: 'SI.5 통합 · 시험',
  SI_6: 'SI.6 인도',
};

const GROUPS = [
  { key: 'PM', name: '사업 관리 PM', names: PM_ACTIVITY_NAME },
  { key: 'SI', name: '구현 현황 SI', names: SI_ACTIVITY_NAME },
] as const;

const toDate = (ms: number): string => new Date(ms).toISOString().slice(0, 10);

const clampPercent = (value: number): number => Math.max(0, Math.min(100, Math.round(value)));

/** 오늘이 구간의 어디쯤인지. 시작 전이면 0, 지났으면 100. */
function plannedAt(start: number, end: number, today: number): number {
  if (end <= start) return today >= end ? 100 : 0;
  return clampPercent(((today - start) / (end - start)) * 100);
}

export interface ActivitySchedule {
  tasks: ScheduleTask[];
  /** 날짜가 추정치임을 화면이 밝히도록 알려준다. */
  datesAreEstimated: boolean;
}

export function buildActivityTasks(
  items: WorkProductResponse[],
  projectStart: string,
  projectEnd: string,
  today: number = Date.now(),
): ActivitySchedule {
  const start = dayOf(projectStart);
  const end = dayOf(projectEnd);
  const tasks: ScheduleTask[] = [];
  if (Number.isNaN(start) || Number.isNaN(end)) return { tasks, datesAreEstimated: true };

  const total = Math.max(DAY_MS, end - start);

  for (const group of GROUPS) {
    const keys = Object.keys(group.names);
    const step = total / keys.length;

    const rows = keys.map((key, index) => {
      const owned = items.filter(
        (w) => w.applicable && (group.key === 'PM' ? w.pmActivity : w.siActivity) === key,
      );
      const approved = owned.filter((w) => w.status === 'APPROVED').length;
      const from = start + step * index;
      const to = index === keys.length - 1 ? end : start + step * (index + 1);

      return {
        id: `${group.key}-${key}`,
        code: key.replace('_', '.'),
        level: 1,
        name: group.names[key],
        owner: `산출물 ${owned.length}종`,
        startAt: toDate(from),
        endAt: toDate(to),
        progress: owned.length === 0 ? 0 : clampPercent((approved / owned.length) * 100),
        planned: plannedAt(from, to, today),
      } satisfies ScheduleTask;
    });

    // 묶음 머리줄 — 아래 활동들의 평균 진척을 이고 있다.
    const progress =
      rows.length === 0
        ? 0
        : clampPercent(rows.reduce((sum, r) => sum + r.progress, 0) / rows.length);

    tasks.push(
      {
        id: group.key,
        code: group.key,
        level: 0,
        name: group.name,
        owner: `활동 ${rows.length}개`,
        startAt: toDate(start),
        endAt: toDate(end),
        progress,
        planned: plannedAt(start, end, today),
      },
      ...rows,
    );
  }

  return { tasks, datesAreEstimated: true };
}
