import { describe, expect, it } from 'vitest';
import { fetchAllPages } from '@/lib/paging';
import type { PageResponse } from '@/types/api';

function pager(total: number) {
  const calls: Array<[number, number]> = [];
  const load = (page: number, size: number): Promise<PageResponse<number>> => {
    calls.push([page, size]);
    const start = page * size;
    const content = Array.from(
      { length: Math.max(0, Math.min(size, total - start)) },
      (_, i) => start + i,
    );
    return Promise.resolve({
      content,
      page,
      size,
      totalElements: total,
      totalPages: Math.ceil(total / size),
      hasNext: start + content.length < total,
    });
  };
  return { load, calls };
}

describe('fetchAllPages', () => {
  it('한 쪽 상한을 넘는 목록도 끝까지 모은다', async () => {
    const { load, calls } = pager(450);
    const rows = await fetchAllPages(load);
    expect(rows).toHaveLength(450);
    expect(rows[449]).toBe(449);
    expect(calls).toEqual([
      [0, 200],
      [1, 200],
      [2, 200],
    ]);
  });

  it('비어 있으면 한 번만 부른다', async () => {
    const { load, calls } = pager(0);
    expect(await fetchAllPages(load)).toEqual([]);
    expect(calls).toHaveLength(1);
  });
});
