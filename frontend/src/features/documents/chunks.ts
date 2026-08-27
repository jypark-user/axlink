import type { DocumentChunkResponse } from '@/types/api';

/**
 * 읽은 본문에 새로 받은 쪽을 이어 붙인다.
 * 색인이 갱신되면 보던 쪽을 다시 받으므로, index 로 겹침을 걸러야 같은 문단이 두 번 쌓이지 않는다.
 */
export const mergeChunks = (
  prev: DocumentChunkResponse[],
  next: DocumentChunkResponse[],
): DocumentChunkResponse[] => {
  const byIndex = new Map(prev.map((c) => [c.index, c]));
  for (const c of next) byIndex.set(c.index, c);
  return [...byIndex.values()].sort((a, b) => a.index - b.index);
};

/** 색인 조각은 앞뒤가 겹치게 잘려 있다 — 겹친 만큼 덜어 내고 이어야 같은 문단이 두 번 나오지 않는다. */
const OVERLAP_MAX = 600;

export const joinChunks = (chunks: { content: string }[]): string =>
  chunks.reduce((text, chunk) => {
    const next = chunk.content;
    if (text === '') return next;
    const window = Math.min(OVERLAP_MAX, text.length, next.length);
    for (let size = window; size >= 40; size -= 1) {
      if (text.endsWith(next.slice(0, size))) return text + next.slice(size);
    }
    return `${text}\n${next}`;
  }, '');
