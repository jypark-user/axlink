import { refreshSession, request } from '@/lib/http';
import { tokenStore } from '@/lib/token-store';
import type {
  AcceptInvitationRequest,
  InvitationPreviewResponse,
  LoginRequest,
  LoginResponse,
  MeResponse,
} from '@/types/api';

export const login = (body: LoginRequest): Promise<LoginResponse> =>
  request<LoginResponse>('/auth/login', { method: 'POST', body, skipAuthRefresh: true });

/** 진행 중인 리프레시가 있으면 그것을 함께 기다린다(토큰 회전 경합 방지). */
export const refresh = (): Promise<LoginResponse | null> => refreshSession();

export const logout = async (): Promise<void> => {
  const refreshToken = tokenStore.refresh;
  try {
    // 인증이 필요한 엔드포인트다 — 액세스 토큰을 함께 보낸다.
    await request<void>('/auth/logout', { method: 'POST', body: { refreshToken } });
  } catch {
    // 서버가 거절하거나 닿지 않아도 이 기기에서는 반드시 로그아웃한다.
  } finally {
    tokenStore.clear();
  }
};

export const getMe = (): Promise<MeResponse> => request<MeResponse>('/auth/me');

export const previewInvitation = (token: string): Promise<InvitationPreviewResponse> =>
  request<InvitationPreviewResponse>(`/auth/invitations/${encodeURIComponent(token)}`, {
    skipAuthRefresh: true,
  });

export const acceptInvitation = (body: AcceptInvitationRequest): Promise<LoginResponse> =>
  request<LoginResponse>('/auth/invitations/accept', {
    method: 'POST',
    body,
    skipAuthRefresh: true,
  });
