import { afterEach, describe, expect, it, vi } from 'vitest';
import { logout } from '@/api/auth';
import { refreshSession } from '@/lib/http';
import { tokenStore } from '@/lib/token-store';

const jsonResponse = (status: number, body: unknown) =>
  new Response(body === null ? '' : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

afterEach(() => {
  vi.restoreAllMocks();
  tokenStore.clear();
});

describe('세션', () => {
  it('서버가 로그아웃을 거절해도 이 기기의 토큰은 지운다', async () => {
    tokenStore.set('access-1', 'refresh-1');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(401, { code: 'TOKEN_INVALID', message: '만료' }),
    );

    await expect(logout()).resolves.toBeUndefined();

    expect(tokenStore.access).toBeNull();
    expect(tokenStore.refresh).toBeNull();
  });

  it('리프레시 토큰은 액세스 토큰과 따로 남는다 — 새로고침 뒤 되살릴 근거', () => {
    tokenStore.set('access-1', 'refresh-1');
    tokenStore.set(null); // 액세스만 버려도(새로고침) 리프레시는 남는다.
    expect(tokenStore.refresh).toBe('refresh-1');
  });

  it('동시에 부른 리프레시는 한 번만 나간다 — 토큰 회전 경합 방지', async () => {
    tokenStore.set('access-1', 'refresh-1');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(200, {
        accessToken: 'access-2',
        refreshToken: 'refresh-2',
        expiresIn: 1800,
        user: { id: 'u1' },
      }),
    );

    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a?.accessToken).toBe('access-2');
    expect(b?.accessToken).toBe('access-2');
    expect(tokenStore.refresh).toBe('refresh-2');
  });
});
