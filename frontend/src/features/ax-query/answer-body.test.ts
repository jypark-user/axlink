import { describe, expect, it } from 'vitest';
import { parseFootnotes } from '@/features/ax-query/answer-body';

describe('parseFootnotes', () => {
  it('각주 번호를 글에서 떼어 낸다', () => {
    const segs = parseFootnotes('이슈는 7건이다[1]. 끝.');
    expect(segs.map((s) => s.kind)).toEqual(['text', 'footnote', 'text']);
    expect(segs[1].footnoteNo).toBe(1);
  });

  it('그림 자리는 각주와 다른 갈래로 읽는다', () => {
    const segs = parseFootnotes('처리 중 이슈다[2].\n[그림 1]\n끝.');
    const figure = segs.find((s) => s.kind === 'figure');
    expect(figure?.slot).toBe(1);
    expect(segs.find((s) => s.kind === 'footnote')?.footnoteNo).toBe(2);
  });

  it('공백이 있어도 그림 자리로 읽는다', () => {
    expect(parseFootnotes('[그림  3]').find((s) => s.kind === 'figure')?.slot).toBe(3);
  });

  it('숫자만 있는 대괄호는 그림이 아니다', () => {
    const segs = parseFootnotes('근거 [1] 과 [12]');
    expect(segs.filter((s) => s.kind === 'figure')).toHaveLength(0);
    expect(segs.filter((s) => s.kind === 'footnote').map((s) => s.footnoteNo)).toEqual([1, 12]);
  });

  it('표식이 없으면 글 한 덩어리다', () => {
    const segs = parseFootnotes('그냥 문장입니다.');
    expect(segs).toHaveLength(1);
    expect(segs[0].kind).toBe('text');
  });
});
