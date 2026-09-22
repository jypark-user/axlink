import { describe, expect, it } from 'vitest';
import { scheduleStatusOf, spanOf } from '@/features/schedule/schedule-task';
import { toScheduleTasks } from '@/features/schedule/wbs-tasks';
import type { WbsItemResponse } from '@/types/api';

const item = (over: Partial<WbsItemResponse>): WbsItemResponse => ({
  wbsId: '1.1',
  name: '착수보고',
  level: 1,
  owner: '',
  deliverable: null,
  startDate: '2026-08-11',
  endDate: '2026-08-11',
  weight: 0.2,
  progress: 100,
  planned: 100,
  externalUrl: null,
  ...over,
});

describe('toScheduleTasks', () => {
  it('서버 값을 그대로 옮기고 계산하지 않는다', () => {
    const [task] = toScheduleTasks([item({ progress: 50, planned: 80 })]);
    expect(task).toEqual({
      id: '1.1',
      code: '1.1',
      level: 1,
      name: '착수보고',
      owner: '',
      startAt: '2026-08-11',
      endAt: '2026-08-11',
      progress: 50,
      planned: 80,
      deliverable: null,
      deliverableStatus: 'NONE',
      deliverableRef: null,
      deliverableUrl: null,
    });
    expect(scheduleStatusOf(task)).toBe('late');
  });

  it('날짜가 없는 항목은 기간 계산에서 빠지되 줄은 남는다', () => {
    const tasks = toScheduleTasks([
      item({ wbsId: '1', level: 0, startDate: null, endDate: null }),
      item({ wbsId: '1.1' }),
    ]);
    expect(tasks).toHaveLength(2);
    expect(tasks[0].startAt).toBe('');
    expect(spanOf(tasks)).toEqual({
      start: Date.parse('2026-08-11T00:00:00'),
      end: Date.parse('2026-08-11T00:00:00'),
    });
  });
});
