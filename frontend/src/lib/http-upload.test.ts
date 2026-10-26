import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, setUnauthorizedHandler } from '@/lib/http';
import { tokenStore } from '@/lib/token-store';

// 업로드는 진행률 때문에 XMLHttpRequest 로 보낸다. 다른 요청처럼 토큰이 만료돼 401 이 오면
// 한 번 갱신하고 한 번만 다시 보낸다(점검 UI-01). 401 이 아닌 실패는 다시 보내지 않는다.

type Reply = { status: number; body?: unknown };

class FakeXhr {
  static replies: Reply[] = [];
  static sent: { auth: string | null; body: unknown }[] = [];
  status = 0;
  responseText = '';
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private headers: Record<string, string> = {};
  open() {}
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send(body: unknown) {
    FakeXhr.sent.push({ auth: this.headers.Authorization ?? null, body });
    const reply = FakeXhr.replies.shift() ?? { status: 500 };
    queueMicrotask(() => {
      if (reply.status === 0) return this.onerror?.();
      this.status = reply.status;
      this.responseText = reply.body === undefined ? '' : JSON.stringify(reply.body);
      this.onload?.();
    });
  }
}

const refreshOk = () =>
  new Response(
    JSON.stringify({
      accessToken: 'new-access',
      refreshToken: 'new-refresh',
      expiresIn: 900,
      user: {},
    }),
    { status: 200 },
  );

describe('api.upload 토큰 갱신', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let onUnauthorized: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    FakeXhr.replies = [];
    FakeXhr.sent = [];
    vi.stubGlobal('XMLHttpRequest', FakeXhr);
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    tokenStore.set('old-access', 'old-refresh');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
    tokenStore.clear();
  });

  it('만료된 토큰이면 한 번 갱신하고 새 토큰으로 한 번만 다시 보낸다', async () => {
    FakeXhr.replies = [{ status: 401 }, { status: 201, body: { id: 'd1' } }];
    fetchMock.mockResolvedValueOnce(refreshOk());
    const form = new FormData();

    await expect(api.upload('/projects/p/documents', form)).resolves.toEqual({ id: 'd1' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(FakeXhr.sent.map((s) => s.auth)).toEqual(['Bearer old-access', 'Bearer new-access']);
    expect(FakeXhr.sent[1].body).toBe(form);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('갱신이 안 되면 다시 보내지 않고 로그인을 푼다', async () => {
    FakeXhr.replies = [{ status: 401 }];
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 401 }));

    await expect(api.upload('/projects/p/documents', new FormData())).rejects.toMatchObject({
      status: 401,
    });
    expect(FakeXhr.sent).toHaveLength(1);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(tokenStore.access).toBeNull();
  });

  it('갱신 뒤에도 401 이면 더 반복하지 않는다', async () => {
    FakeXhr.replies = [{ status: 401 }, { status: 401 }, { status: 201 }];
    fetchMock.mockResolvedValue(refreshOk());

    await expect(api.upload('/projects/p/documents', new FormData())).rejects.toMatchObject({
      status: 401,
    });
    expect(FakeXhr.sent).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('401 이 아닌 실패는 다시 보내지 않는다(접수가 두 번 되지 않게)', async () => {
    for (const reply of [
      { status: 400, body: { code: 'VALIDATION_FAILED' } },
      { status: 500 },
      { status: 0 },
    ]) {
      FakeXhr.replies = [reply, { status: 201 }];
      FakeXhr.sent = [];
      await expect(api.upload('/projects/p/documents', new FormData())).rejects.toBeTruthy();
      expect(FakeXhr.sent).toHaveLength(1);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('정상이면 한 번만 보낸다', async () => {
    FakeXhr.replies = [{ status: 201, body: { id: 'd2' } }];
    await expect(api.upload('/projects/p/documents', new FormData())).resolves.toEqual({
      id: 'd2',
    });
    expect(FakeXhr.sent).toHaveLength(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
