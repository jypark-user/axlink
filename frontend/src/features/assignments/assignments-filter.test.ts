import { describe, expect, it } from 'vitest';
import { filterAssignments } from '@/features/assignments/assignments-filter';
import type { AssignmentResponse } from '@/types/api';

const row = (org: string, name: string, login: string): AssignmentResponse => ({
  id: login,
  projectId: 'p1',
  contractorOrgId: org,
  contractorOrgName: org,
  userId: login,
  userName: name,
  userEmail: login,
  status: 'ACTIVE',
  assignedAt: '2026-11-20T00:00:00Z',
});

describe('용역사 계정 검색', () => {
  const rows = [row('유저인사이트', '박진용', 'wlsdyd04'), row('에이비씨', '김하나', 'Hana01')];

  it('업체명·이름·아이디 어느 것으로도 찾고 대소문자는 가리지 않는다', () => {
    expect(filterAssignments(rows, '인사이트').map((r) => r.id)).toEqual(['wlsdyd04']);
    expect(filterAssignments(rows, '김하').map((r) => r.id)).toEqual(['Hana01']);
    expect(filterAssignments(rows, 'hana').map((r) => r.id)).toEqual(['Hana01']);
  });

  it('빈 검색어는 모두 보이고 맞는 것이 없으면 빈 목록이다', () => {
    expect(filterAssignments(rows, '  ')).toHaveLength(2);
    expect(filterAssignments(rows, '없는말')).toEqual([]);
  });
});
