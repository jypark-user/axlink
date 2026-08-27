import type { ReactNode } from 'react';
import { SidebarTrigger } from '@/components/ui/sidebar';
import { ProjectSwitcher } from '@/components/layout/project-switcher';

export function AppHeader({
  leading,
  trailing,
  children,
}: {
  leading?: ReactNode;
  trailing?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-2 px-3">
      <SidebarTrigger />
      <ProjectSwitcher />
      {leading}
      <div className="flex min-w-0 flex-1 items-center gap-2 truncate text-sm font-medium">
        {children}
      </div>
      <div className="flex items-center gap-2">{trailing}</div>
    </header>
  );
}
