import { describe, expect, it } from 'vitest';
import { mergeChunks } from '@/features/documents/chunks';

const chunk = (index: number, content = `본문 ${index}`) => ({ index, content });

describe('mergeChunks', () => {
  it('다음 쪽을 뒤에 이어 붙인다', () => {
    const merged = mergeChunks([chunk(0), chunk(1)], [chunk(2), chunk(3)]);
    expect(merged.map((c) => c.index)).toEqual([0, 1, 2, 3]);
  });

  it('같은 쪽을 다시 받아도 늘지 않고 새 내용으로 덮는다', () => {
    const merged = mergeChunks([chunk(0, '옛 본문'), chunk(1)], [chunk(0, '새 본문'), chunk(1)]);
    expect(merged).toHaveLength(2);
    expect(merged[0]?.content).toBe('새 본문');
  });

  it('늦게 도착한 쪽도 index 순서대로 꽂는다', () => {
    const merged = mergeChunks([chunk(2), chunk(3)], [chunk(0), chunk(1)]);
    expect(merged.map((c) => c.index)).toEqual([0, 1, 2, 3]);
  });
});
