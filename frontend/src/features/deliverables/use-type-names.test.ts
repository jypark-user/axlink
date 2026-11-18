import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useTypeNames } from '@/features/deliverables/use-type-names';

// 29110 산출물 유형은 코드(TEST_REPORT) 대신 이름(시험결과서)으로 보인다. 이름은 서버의 인도
// 점검표가 단일 원천이다(화면에 목록을 따로 두지 않는다).

const get = vi.fn((_path: string) =>
  Promise.resolve({
    items: [
      { type: 'TEST_REPORT', displayName: '시험결과서' },
      { type: 'SOFTWARE_DESIGN', displayName: '설계서' },
    ],
  }),
);
vi.mock('@/lib/http', () => ({ api: { get: (path: string) => get(path) } }));

describe('산출물 유형 이름', () => {
  it('코드를 인도 점검표의 이름으로 바꾼다', async () => {
    const { result } = renderHook(() => useTypeNames('p1'));
    await waitFor(() => expect(result.current.TEST_REPORT).toBe('시험결과서'));
    expect(result.current.SOFTWARE_DESIGN).toBe('설계서');
    expect(get).toHaveBeenCalledWith('/projects/p1/work-products');
  });

  it('사업이 없으면 묻지 않는다', () => {
    get.mockClear();
    const { result } = renderHook(() => useTypeNames(''));
    expect(result.current).toEqual({});
    expect(get).not.toHaveBeenCalled();
  });
});
