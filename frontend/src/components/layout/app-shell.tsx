import type { CSSProperties, ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { AppHeader } from '@/components/layout/app-header';
import { AppSidebar } from '@/components/layout/app-sidebar';

/** 오른쪽 사이드바 자리. 내용은 화면이 포털로 넣는다 — 그래야 그 화면의 문맥을 그대로 쓴다. */
export const RESOURCE_DOCK_ID = 'ax-resource-dock';

/** 머리줄까지 덮는 배경 자리. 본문 여백 안쪽이 아니라 칸 전체를 채운다. */
export const BACKDROP_SLOT_ID = 'ax-backdrop';

const SHELL_SIZING = {
  '--sidebar-width': '18rem',
  '--sidebar-width-icon': '3.5rem',
} as CSSProperties;

export function AppShell({ children }: { children?: ReactNode }) {
  return (
    <SidebarProvider className="bg-background h-full min-h-0 overflow-hidden" style={SHELL_SIZING}>
      <AppSidebar />

      <SidebarInset className="min-h-0 min-w-0 flex-row overflow-hidden">
        <div className="bg-background relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {/* 머리줄 뒤까지 깔린다 — 본문은 z-10 으로 그 위에 올린다. */}
          <div id={BACKDROP_SLOT_ID} className="contents" />

          <div className="relative z-10 flex min-h-0 min-w-0 flex-1 flex-col">
            <AppHeader />

            <main className="min-h-0 min-w-0 flex-1 overflow-auto p-4 md:p-6">
              {children ?? <Outlet />}
            </main>
          </div>
        </div>

        <div id={RESOURCE_DOCK_ID} className="contents" />
      </SidebarInset>
    </SidebarProvider>
  );
}
