import { useState } from 'react';
import { Settings } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useSidebar } from '@/components/ui/sidebar';
import { useAuth } from '@/features/auth/auth-context';
import { useNavigate } from 'react-router-dom';
import { PasswordDialog } from '@/features/auth/password-dialog';
import { SettingsDialog } from '@/features/settings/settings-dialog';
import { cn } from '@/lib/utils';
import type { Role } from '@/types/api';

const ROLE_LABEL: Record<Role, string> = {
  SUPER_ADMIN: '플랫폼 관리자',
  CLIENT: '고객사',
  CONTRACTOR: '용역사',
};

const initials = (name: string) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase() || 'U';

export function UserMenu() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const { state, isMobile } = useSidebar();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  if (!me) return null;

  const collapsed = state === 'collapsed' && !isMobile;

  return (
    <>
      <div className={cn('flex gap-1', collapsed ? 'flex-col items-center' : 'items-center')}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              title={`${me.name} · ${me.organizationName}`}
              className={cn(
                'gap-2 px-2 hover:bg-transparent hover:text-current',
                collapsed ? 'size-9 p-0' : 'min-w-0 flex-1 justify-start',
              )}
            >
              <Avatar className="size-7">
                <AvatarFallback>{initials(me.name)}</AvatarFallback>
              </Avatar>
              {!collapsed && (
                <div className="flex min-w-0 flex-col items-start overflow-hidden">
                  <span className="truncate text-sm font-medium">{me.name}</span>
                  <span className="text-muted-foreground truncate text-xs">
                    {me.organizationName}
                  </span>
                </div>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side={collapsed ? 'right' : 'top'} align="start" className="w-56">
            <DropdownMenuLabel className="flex flex-col gap-0.5">
              <span>{me.name}</span>
              <span className="text-muted-foreground text-xs font-normal">{me.username}</span>
              <span className="text-muted-foreground text-xs font-normal">
                {me.organizationName} · {ROLE_LABEL[me.role]}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                setSettingsOpen(true);
              }}
            >
              설정
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                setPasswordOpen(true);
              }}
            >
              비밀번호 바꾸기
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={async (e) => {
                e.preventDefault();
                await logout();
                void navigate('/login', { replace: true });
              }}
            >
              로그아웃
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          variant="ghost"
          size="icon"
          aria-haspopup="dialog"
          title="설정"
          className="text-muted-foreground size-8 shrink-0"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings className="size-4" />
          <span className="sr-only">설정</span>
        </Button>
      </div>
      {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}
      {passwordOpen && <PasswordDialog onClose={() => setPasswordOpen(false)} />}
    </>
  );
}
