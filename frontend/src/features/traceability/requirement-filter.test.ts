import { describe, expect, it } from 'vitest';
import {
  filterLabel,
  filterParams,
  implementedNote,
  NO_FILTER,
  rateText,
  sameFilter,
} from '@/features/traceability/requirement-filter';

describe('요구사항 목록 조건', () => {
  it('카드마다 서버 쿼리가 하나로 정해진다', () => {
    expect(filterParams(NO_FILTER)).toEqual({});
    expect(filterParams({ kind: 'verified', value: true })).toEqual({ verified: true });
    expect(filterParams({ kind: 'verified', value: false })).toEqual({ verified: false });
    expect(filterParams({ kind: 'status', status: 'IMPLEMENTED' })).toEqual({
      status: 'IMPLEMENTED',
    });
    expect(
      filterParams({
        kind: 'source',
        connectionId: 'c1',
        sourceLabel: 'GitHub a/b',
        state: 'CLOSED',
      }),
    ).toEqual({ sourceState: 'CLOSED', connectionId: 'c1' });
    expect(
      filterParams({
        kind: 'source',
        connectionId: null,
        sourceLabel: '원천 연결 없음',
        state: 'NONE',
      }),
    ).toEqual({ sourceState: 'NONE' });
  });

  it('검증 미완료를 미구현이라고 부르지 않는다', () => {
    expect(filterLabel({ kind: 'verified', value: false })).toBe('검증 미완료');
    expect(filterLabel(NO_FILTER)).toBeNull();
    expect(
      filterLabel({
        kind: 'source',
        connectionId: 'c1',
        sourceLabel: 'GitHub a/b',
        state: 'CLOSED',
      }),
    ).toBe('GitHub a/b · 원천 이슈 닫힘');
  });

  it('분모가 0 이면 비율은 산출 불가다', () => {
    expect(rateText(null)).toBe('산출 불가');
    expect(rateText(0)).toBe('0%');
    expect(rateText(11 / 41)).toBe('26.8%');
  });

  it('같은 조건을 다시 누르면 같은 조건으로 본다', () => {
    expect(sameFilter({ kind: 'verified', value: true }, { kind: 'verified', value: true })).toBe(
      true,
    );
    expect(sameFilter({ kind: 'verified', value: true }, NO_FILTER)).toBe(false);
  });
});

describe('구현 칸 설명', () => {
  const base = {
    total: 41,
    verified: 0,
    notVerified: 41,
    verifiedRate: 0,
    decided: 0,
    sources: [],
  };
  const byStatus = (implemented: number) => [
    { status: 'DEFINED' as const, count: 41 - implemented },
    { status: 'IMPLEMENTED' as const, count: implemented },
  ];

  it('구현이 전부 원천 이슈 닫힘에서 왔으면 모두라고 말한다', () => {
    const text = implementedNote({
      ...base,
      byStatus: byStatus(11),
      implementedFromSourceClosed: 11,
    });
    expect(text).toBe(
      '구현 11건은 모두 GitHub 원천 이슈가 닫혀서 붙은 상태입니다. 구현·검증 완료를 뜻하지 않습니다.',
    );
  });

  it('일부만 원천 이슈 닫힘이면 그 건수만 짚는다', () => {
    const text = implementedNote({
      ...base,
      byStatus: byStatus(11),
      implementedFromSourceClosed: 4,
    });
    expect(text.startsWith('구현 11건 중 4건은')).toBe(true);
  });
});
