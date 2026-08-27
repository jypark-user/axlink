type Listener = () => void;

const REFRESH_KEY = 'axlink.refresh';
const listeners = new Set<Listener>();
let accessToken: string | null = null;

/**
 * 리프레시 토큰은 localStorage 에 둔다 — 탭을 새로 열거나 브라우저를 껐다 켜도 로그인이 남는다.
 * 매번 저장소를 읽으므로 다른 탭이 토큰을 회전시켜도 이 탭이 낡은 토큰을 쓰지 않는다.
 * 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서는 메모리에만 들고 간다.
 */
const storage: Storage | null = (() => {
  try {
    const probe = '__axlink_probe__';
    localStorage.setItem(probe, '1');
    localStorage.removeItem(probe);
    return localStorage;
  } catch {
    return null;
  }
})();

let refreshMemo: string | null = storage?.getItem(REFRESH_KEY) ?? null;

const currentRefresh = (): string | null => (storage ? storage.getItem(REFRESH_KEY) : refreshMemo);

function writeRefresh(token: string | null): void {
  refreshMemo = token;
  if (!storage) return;
  if (token) storage.setItem(REFRESH_KEY, token);
  else storage.removeItem(REFRESH_KEY);
}

export const tokenStore = {
  get access(): string | null {
    return accessToken;
  },
  get refresh(): string | null {
    return currentRefresh();
  },
  set(access: string | null, refresh: string | null = currentRefresh()): void {
    accessToken = access;
    writeRefresh(refresh);
    listeners.forEach((l) => l());
  },
  clear(): void {
    accessToken = null;
    writeRefresh(null);
    listeners.forEach((l) => l());
  },
  subscribe(l: Listener): () => void {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};
