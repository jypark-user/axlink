import { describe, expect, it } from 'vitest';
import { pageWindow } from '@/components/ui/pagination';

describe('pageWindow', () => {
  it('7쪽 이하는 전부 보여 준다', () => {
    expect(pageWindow(0, 5)).toEqual([0, 1, 2, 3, 4]);
    expect(pageWindow(3, 7)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it('쪽이 많아도 자리는 7칸이고 첫 쪽·끝 쪽은 항상 남는다', () => {
    for (const cur of [0, 1, 5, 9, 19]) {
      const w = pageWindow(cur, 20);
      expect(w).toHaveLength(7);
      expect(w[0]).toBe(0);
      expect(w[6]).toBe(19);
      expect(w).toContain(cur);
    }
  });

  it('앞·뒤 끝에서는 한쪽만 끊는다', () => {
    expect(pageWindow(0, 10)).toEqual([0, 1, 2, 3, 4, 'gap', 9]);
    expect(pageWindow(9, 10)).toEqual([0, 'gap', 5, 6, 7, 8, 9]);
    expect(pageWindow(5, 10)).toEqual([0, 'gap', 4, 5, 6, 'gap', 9]);
  });
});
