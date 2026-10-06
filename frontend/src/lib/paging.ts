import type { PageResponse } from '@/types/api';

/** 서버가 받는 한 쪽 최대 크기. 라우터의 size 상한(le=200)과 같다. */
export const MAX_PAGE_SIZE = 200;

/**
 * 목록을 끝까지 받는다. 화면 표가 검색·정렬을 손에서 하므로 일부만 받으면 나머지 행에 닿지 못한다.
 * 서버가 준 totalElements 만큼 모일 때까지 쪽을 넘긴다. 쪽이 비면 거기서 멈춘다.
 */
export async function fetchAllPages<T>(
  load: (page: number, size: number) => Promise<PageResponse<T>>,
  size: number = MAX_PAGE_SIZE,
): Promise<T[]> {
  const rows: T[] = [];
  for (let page = 0; ; page += 1) {
    const res = await load(page, size);
    rows.push(...res.content);
    if (res.content.length === 0 || rows.length >= res.totalElements || !res.hasNext) {
      return rows;
    }
  }
}
