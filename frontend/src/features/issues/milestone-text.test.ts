import { describe, expect, it } from 'vitest';
import { localToday, milestoneText } from '@/features/issues/milestone-text';

const m4 = { title: 'M4 통합 PoC 완성', dueOn: '2026-10-23', state: 'OPEN', url: null } as const;

describe('이슈의 원천 마일스톤 표시', () => {
  it('이름·기한·상태를 원천 값 그대로 쓴다', () => {
    expect(milestoneText(m4, '2026-10-20')).toEqual({
      text: 'M4 통합 PoC 완성 · 10-23 · 진행 중',
      due: '10-23',
      overdue: false,
    });
    expect(milestoneText({ ...m4, state: 'CLOSED' }, '2026-11-02').text).toBe(
      'M4 통합 PoC 완성 · 10-23 · 완료',
    );
  });

  it('없으면 미지정, 기한 없는 마일스톤은 기한을 빼고 쓴다', () => {
    expect(milestoneText(null, '2026-11-02').text).toBe('미지정');
    expect(milestoneText({ ...m4, dueOn: null }, '2026-11-02')).toEqual({
      text: 'M4 통합 PoC 완성 · 진행 중',
      due: null,
      overdue: false,
    });
  });

  it('기한이 지났는데 열려 있을 때만 강조한다. 닫힌 것은 강조하지 않는다', () => {
    expect(milestoneText(m4, '2026-11-02').overdue).toBe(true);
    expect(milestoneText(m4, '2026-10-23').overdue).toBe(false);
    expect(milestoneText({ ...m4, state: 'CLOSED' }, '2026-11-02').overdue).toBe(false);
  });

  it('오늘 날짜를 YYYY-MM-DD 로 만든다', () => {
    expect(localToday(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});
