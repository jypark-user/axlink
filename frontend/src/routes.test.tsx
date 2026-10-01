import { render, screen } from '@testing-library/react';
import { MemoryRouter, Outlet } from 'react-router-dom';
import { vi } from 'vitest';
import { AppRoutes } from '@/routes';
import type { MeResponse, Role } from '@/types/api';

// 라우트 배치만 본다. 셸과 화면 본체는 API 를 부르므로 이름표로 바꾼다.
const auth = vi.hoisted(() => ({ me: null as MeResponse | null }));

vi.mock('@/features/auth/auth-context', () => ({
  useAuth: () => ({ me: auth.me, status: auth.me ? 'authenticated' : 'anonymous' }),
}));
vi.mock('@/components/layout/app-shell', () => ({ AppShell: () => <Outlet /> }));
vi.mock('@/features/templates/templates-page', () => ({
  TemplatesPage: () => <h1>템플릿 화면</h1>,
}));
vi.mock('@/features/admin/error-log-page', () => ({
  ErrorLogPage: () => <h1>오류 기록 화면</h1>,
}));

function signIn(role: Role): void {
  auth.me = {
    userId: 'u1',
    username: 'u1',
    name: '사용자',
    role,
    organizationId: 'o1',
    organizationName: '기관',
    organizationType: role === 'CONTRACTOR' ? 'CONTRACTOR' : 'CLIENT',
    allowedProjectIds: [],
  };
}

function visit(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('관리자 전용 화면', () => {
  it.each([
    ['/templates', '템플릿 화면'],
    ['/admin/errors', '오류 기록 화면'],
  ])('최고관리자는 %s 에 들어간다', async (path, heading) => {
    signIn('SUPER_ADMIN');
    visit(path);
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument();
  });

  it.each([
    ['CLIENT', '/templates'],
    ['CLIENT', '/admin/errors'],
    ['CONTRACTOR', '/templates'],
    ['CONTRACTOR', '/admin/errors'],
  ] as const)('%s 는 %s 에서 권한 없음으로 간다', async (role, path) => {
    signIn(role);
    visit(path);
    expect(await screen.findByRole('heading', { name: '접근 권한이 없습니다' })).toBeInTheDocument();
  });
});
