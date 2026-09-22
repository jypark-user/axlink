import type { ScheduleTask } from '@/features/schedule/schedule-task';
import type { WbsItemResponse } from '@/types/api';

/**
 * 서버가 준 WBS 항목을 일정 화면의 작업 줄로 옮긴다. 계산은 없다 — 진척·계획선은 서버가
 * 이미 냈고(메뉴와 질의가 같은 값을 봐야 한다), 여기서는 모양만 맞춘다.
 * 날짜가 없는 항목은 빈 문자열로 둔다. 간트·캘린더는 그런 줄을 건너뛰고 WBS 표는 보여 준다.
 */
export function toScheduleTasks(items: WbsItemResponse[]): ScheduleTask[] {
  return items.map((item) => ({
    id: item.wbsId,
    code: item.wbsId,
    level: item.level,
    name: item.name,
    owner: item.owner,
    startAt: item.startDate ?? '',
    endAt: item.endDate ?? '',
    progress: item.progress,
    planned: item.planned,
    deliverable: item.deliverable,
    deliverableStatus: item.deliverableStatus ?? 'NONE',
    deliverableRef: item.deliverableRef ?? null,
    deliverableUrl: item.deliverableUrl ?? null,
  }));
}
