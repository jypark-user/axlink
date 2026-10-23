import { ApiError } from '@/lib/api-error';
import { tokenStore } from '@/lib/token-store';
import type { LoginResponse, RefreshResponse } from '@/types/api';

// 앱 경로 아래의 /api 다. 외부 공개(/ax-link/)에서 도메인 맨 앞의 /api 로 새지 않게 한다.
const BASE = `${import.meta.env.BASE_URL}api`;

export type ApiInit = Omit<RequestInit, 'body'> & {
  body?: unknown;
  skipAuthRefresh?: boolean;
};

let unauthorizedHandler: (() => void) | null = null;
let refreshInflight: Promise<LoginResponse | null> | null = null;

export const setUnauthorizedHandler = (fn: (() => void) | null) => {
  unauthorizedHandler = fn;
};

/**
 * 리프레시는 한 번에 하나만 나간다. 서버가 리프레시 토큰을 회전(옛 토큰 폐기)시키므로
 * 동시에 두 번 부르면 늦은 쪽이 실패해 멀쩡한 로그인이 풀린다.
 */
export async function refreshSession(): Promise<LoginResponse | null> {
  const refresh = tokenStore.refresh;
  if (!refresh) return null;
  if (refreshInflight) return refreshInflight;
  refreshInflight = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken: refresh }),
      });
      const payload = await safeJson(res);
      if (!res.ok) return null;
      const data = payload as RefreshResponse;
      tokenStore.set(data.accessToken, data.refreshToken);
      return {
        accessToken: data.accessToken,
        refreshToken: data.refreshToken,
        expiresIn: data.expiresIn,
        user: data.user,
      };
    } catch {
      return null;
    } finally {
      refreshInflight = null;
    }
  })();
  return refreshInflight;
}

async function safeJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function withAuth(headers: Headers, init: ApiInit): Headers {
  const h = new Headers(headers);
  if (!init.skipAuthRefresh) {
    const access = tokenStore.access;
    if (access) h.set('Authorization', `Bearer ${access}`);
  }
  return h;
}

export async function request<T>(path: string, init: ApiInit = {}): Promise<T> {
  const url = path.startsWith('http') ? path : `${BASE}${path}`;
  const headers = withAuth(new Headers(init.headers), init);
  const isForm = init.body instanceof FormData;
  if (!isForm && init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const body: BodyInit | undefined = isForm
    ? (init.body as FormData)
    : init.body !== undefined
      ? JSON.stringify(init.body)
      : undefined;

  let res = await fetch(url, { ...init, headers, body });

  if (res.status === 401 && !init.skipAuthRefresh) {
    const refreshed = await refreshSession();
    if (refreshed) {
      const retryHeaders = withAuth(new Headers(init.headers), init);
      if (!isForm && init.body !== undefined && !retryHeaders.has('Content-Type')) {
        retryHeaders.set('Content-Type', 'application/json');
      }
      res = await fetch(url, {
        ...init,
        headers: retryHeaders,
        body: isForm
          ? (init.body as FormData)
          : init.body !== undefined
            ? JSON.stringify(init.body)
            : undefined,
      });
    } else {
      tokenStore.clear();
      unauthorizedHandler?.();
    }
  }

  if (res.status === 204) return undefined as T;
  const payload = await safeJson(res);
  if (!res.ok) throw ApiError.from(res.status, payload);
  return payload as T;
}

export function requestMultipart<T>(path: string, form: FormData, init: ApiInit = {}): Promise<T> {
  return request<T>(path, { ...init, method: init.method ?? 'POST', body: form });
}

export async function openStream(
  path: string,
  body: unknown,
  signal: AbortSignal,
): Promise<Response> {
  const url = `${BASE}${path}`;
  const headers = withAuth(new Headers({ Accept: 'text/event-stream' }), {});
  headers.set('Content-Type', 'application/json');
  let res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal });

  if (res.status === 401) {
    const refreshed = await refreshSession();
    if (refreshed) {
      const retryHeaders = withAuth(new Headers({ Accept: 'text/event-stream' }), {});
      retryHeaders.set('Content-Type', 'application/json');
      res = await fetch(url, {
        method: 'POST',
        headers: retryHeaders,
        body: JSON.stringify(body),
        signal,
      });
    } else {
      tokenStore.clear();
      unauthorizedHandler?.();
    }
  }
  if (!res.ok || !res.body) {
    const payload = await safeJson(res);
    throw ApiError.from(res.status, payload);
  }
  return res;
}

/**
 * 파일을 Blob 으로 받는다. 토큰이 헤더로 가야 해서 img·a 에 주소를 그냥 걸 수 없을 때 쓴다.
 */
export async function fetchBlob(path: string): Promise<Blob> {
  const url = `${BASE}${path}`;
  let res = await fetch(url, { headers: withAuth(new Headers(), {}) });
  if (res.status === 401) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      tokenStore.clear();
      unauthorizedHandler?.();
      throw new ApiError(401, 'UNAUTHORIZED', '로그인이 필요합니다.');
    }
    res = await fetch(url, { headers: withAuth(new Headers(), {}) });
  }
  if (!res.ok) throw ApiError.from(res.status, await safeJson(res));
  return res.blob();
}

/**
 * 파일을 받아 브라우저 내려받기로 넘긴다.
 * 토큰이 헤더로 가야 해서 링크를 그냥 걸 수 없다 — 받아 온 뒤 잠시 만든 주소로 넘긴다.
 */
export async function download(path: string, filename: string): Promise<void> {
  const href = URL.createObjectURL(await fetchBlob(path));
  const link = document.createElement('a');
  link.href = href;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(href);
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  del: <T>(path: string, body?: unknown) => request<T>(path, { method: 'DELETE', body }),
  upload: <T>(path: string, form: FormData, onProgress?: (ratio: number) => void) =>
    uploadXhr<T>(path, form, onProgress),
  download,
};

function uploadXhr<T>(
  path: string,
  form: FormData,
  onProgress?: (ratio: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}${path}`);
    const access = tokenStore.access;
    if (access) xhr.setRequestHeader('Authorization', `Bearer ${access}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let payload: unknown;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        payload = null;
      }
      if (xhr.status === 204) return resolve(undefined as T);
      if (xhr.status >= 200 && xhr.status < 300) return resolve(payload as T);
      reject(ApiError.from(xhr.status, payload));
    };
    xhr.onerror = () => reject(new ApiError(0, 'NETWORK', '네트워크 오류가 발생했습니다.'));
    xhr.send(form);
  });
}
