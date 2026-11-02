import type { IssueMilestone } from '@/types/api';

/**
 * 이슈의 원천 마일스톤 표시(ARC-023). "M4 통합 PoC 완성 · 10-23 · 진행 중".
 * 기한이 지났는데 열려 있으면 overdue 만 알린다. "지연" 판정·건수는 내지 않는다(일정 준수율 몫이다).
 */
export function milestoneText(
  m: IssueMilestone | null | undefined,
  today: string,
): { text: string; due: string | null; overdue: boolean } {
  if (!m) return { text: '미지정', due: null, overdue: false };
  const state = m.state === 'CLOSED' ? '완료' : '진행 중';
  const due = m.dueOn ? m.dueOn.slice(5) : null;
  const overdue = m.state !== 'CLOSED' && m.dueOn !== null && m.dueOn < today;
  return { text: [m.title, due, state].filter(Boolean).join(' · '), due, overdue };
}

/** 사업 시간대가 아니라 보는 사람의 오늘. 강조에만 쓴다. */
export function localToday(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}
