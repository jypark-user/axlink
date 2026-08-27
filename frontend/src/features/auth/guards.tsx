import { type ReactElement, type ReactNode } from 'react';
import { Navigate, Outlet, useLocation, useParams } from 'react-router-dom';
import { useAuth } from '@/features/auth/auth-context';
import { Skeleton } from '@/components/ui/skeleton';
import type { Role } from '@/types/api';

export const RequireAuth = ({ children }: { children: ReactNode }): ReactElement => {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'booting') {
    return (
      <div className="flex h-svh items-center justify-center">
        <Skeleton className="h-8 w-48" />
      </div>
    );
  }
  if (status !== 'authenticated') {
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }
  return <>{children}</>;
};

/** children 없이 쓰면 레이아웃 라우트로 동작한다 — 하위 라우트 묶음에 한 번만 건다. */
export const RequireRole = ({
  allow,
  children,
}: {
  allow: Role[];
  children?: ReactNode;
}): ReactElement => {
  const { me } = useAuth();
  if (!me || !allow.includes(me.role)) {
    return <Navigate to="/403" replace />;
  }
  return <>{children ?? <Outlet />}</>;
};

/**
 * 사업 접근은 서버가 판정한다. 로그인 때 받은 허용 목록은 금세 낡아서 —
 * 방금 만든 사업이나 방금 받은 할당이 빠져 있어 — 멀쩡한 접근을 막았다.
 * 여기서는 주소만 보고, 실제 거절은 ProjectShell 이 조회 결과(403·404)로 처리한다.
 */
export const RequireProject = ({ children }: { children: ReactNode }): ReactElement => {
  const { projectId } = useParams();
  const { me } = useAuth();
  if (!me || !projectId) {
    return <Navigate to="/403" replace />;
  }
  return <>{children}</>;
};
