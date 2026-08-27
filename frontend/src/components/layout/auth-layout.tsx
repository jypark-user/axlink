import { type ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';

export function AuthLayout({ children }: { children?: ReactNode }): ReactNode {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-muted/40 p-4">
      <div className="mb-6 flex items-center gap-2 text-lg font-semibold">
        <ShieldCheck className="size-6 text-primary" />
        <span>AX-Link</span>
      </div>
      {children ?? <Outlet />}
    </div>
  );
}
