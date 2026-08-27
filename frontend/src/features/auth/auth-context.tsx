import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  getMe,
  login as loginApi,
  logout as logoutApi,
  refresh as refreshApi,
  acceptInvitation as acceptInviteApi,
} from '@/api/auth';
import { setUnauthorizedHandler } from '@/lib/http';
import { tokenStore } from '@/lib/token-store';
import type { AcceptInvitationRequest, LoginRequest, LoginResponse, MeResponse } from '@/types/api';

export type AuthStatus = 'booting' | 'authenticated' | 'anonymous';

interface AuthContextValue {
  me: MeResponse | null;
  status: AuthStatus;
  login: (body: LoginRequest) => Promise<MeResponse>;
  acceptInvite: (body: AcceptInvitationRequest) => Promise<MeResponse>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [status, setStatus] = useState<AuthStatus>('booting');
  const mounted = useRef(true);

  const goAnonymous = useCallback(() => {
    if (mounted.current) {
      setMe(null);
      setStatus('anonymous');
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    setUnauthorizedHandler(goAnonymous);
    let cancelled = false;
    void (async () => {
      const refreshed = await refreshApi();
      if (cancelled) return;
      if (refreshed) {
        tokenStore.set(refreshed.accessToken, refreshed.refreshToken);
        setMe(refreshed.user);
        setStatus('authenticated');
      } else {
        tokenStore.clear();
        setStatus('anonymous');
      }
    })();
    return () => {
      cancelled = true;
      mounted.current = false;
    };
  }, [goAnonymous]);

  const applySession = useCallback((res: LoginResponse) => {
    tokenStore.set(res.accessToken, res.refreshToken);
    if (mounted.current) setMe(res.user);
    setStatus('authenticated');
  }, []);

  const login = useCallback(
    async (body: LoginRequest): Promise<MeResponse> => {
      const res = await loginApi(body);
      applySession(res);
      return res.user;
    },
    [applySession],
  );

  const acceptInvite = useCallback(
    async (body: AcceptInvitationRequest): Promise<MeResponse> => {
      const res = await acceptInviteApi(body);
      applySession(res);
      return res.user;
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await logoutApi();
    } finally {
      // 서버 응답이 어떻든 이 기기는 로그아웃 상태로 간다.
      tokenStore.clear();
      setMe(null);
      setStatus('anonymous');
    }
  }, []);

  const refreshMe = useCallback(async () => {
    try {
      const next = await getMe();
      if (mounted.current) setMe(next);
    } catch {
      if (mounted.current) {
        setMe(null);
        setStatus('anonymous');
      }
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ me, status, login, acceptInvite, logout, refreshMe }),
    [me, status, login, acceptInvite, logout, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};
