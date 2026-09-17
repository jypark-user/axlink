import { useMemo, useState } from 'react';
import { Check, Cpu, Settings as SettingsIcon, User as UserIcon } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { SearchInput } from '@/components/ui/search-input';
import { Separator } from '@/components/ui/separator';
import { useAuth } from '@/features/auth/auth-context';
import { LlmSettingsSection } from '@/features/settings/llm-settings-section';
import { themeModeLabel, useTheme, type ThemeMode } from '@/features/settings/theme-context';
import { cn } from '@/lib/utils';
import type { Role } from '@/types/api';

type SectionId = 'general' | 'account' | 'ai';

const THEME_MODES: ThemeMode[] = ['light', 'dark', 'system'];

const SECTION_LABEL: Record<SectionId, string> = {
  general: '일반',
  account: '계정',
  ai: 'AI 모델',
};

const ROLE_LABEL: Record<Role, string> = {
  SUPER_ADMIN: '플랫폼 관리자',
  CLIENT: '고객사',
  CONTRACTOR: '용역사',
};

const ROW = 'flex items-center justify-between gap-4 py-3';

function GeneralSection() {
  const { mode, setMode } = useTheme();
  return (
    <div className="flex flex-col">
      <div className={ROW}>
        <div className="flex flex-col gap-0.5">
          <span className="text-sm font-medium">화면 모드</span>
          <span className="text-muted-foreground text-xs">
            시스템 설정을 고르면 기기 설정을 따릅니다.
          </span>
        </div>
        <div className="flex shrink-0 gap-1">
          {THEME_MODES.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMode(option)}
              aria-pressed={mode === option}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm transition-colors',
                mode === option
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )}
            >
              {themeModeLabel[option]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function AccountSection() {
  const { me } = useAuth();
  if (!me) return null;
  const rows: Array<[string, string]> = [
    ['이름', me.name],
    ['아이디', me.username],
    ['소속', me.organizationName],
    ['역할', ROLE_LABEL[me.role]],
    ['접근 가능 프로젝트', `${me.allowedProjectIds.length}건`],
  ];
  return (
    <div className="flex flex-col">
      {rows.map(([label, value], index) => (
        <div key={label}>
          {index > 0 && <Separator />}
          <div className={ROW}>
            <span className="text-muted-foreground text-sm">{label}</span>
            <span className="truncate text-sm font-medium">{value}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [section, setSection] = useState<SectionId>('general');
  const [query, setQuery] = useState('');
  const { me } = useAuth();
  const isAdmin = me?.role === 'SUPER_ADMIN';

  const groups = useMemo(() => {
    const all = [
      {
        label: '설정',
        items: [
          { id: 'general' as const, label: '일반', icon: SettingsIcon },
          { id: 'account' as const, label: '계정', icon: UserIcon },
          // AI 모델 설정은 플랫폼 전체에 하나라 관리자만 본다 (ARC-011)
          ...(isAdmin ? [{ id: 'ai' as const, label: 'AI 모델', icon: Cpu }] : []),
        ],
      },
    ];
    const keyword = query.trim();
    if (!keyword) return all;
    return all
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => item.label.includes(keyword)),
      }))
      .filter((group) => group.items.length > 0);
  }, [query, isAdmin]);

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex h-[min(660px,90vh)] max-w-4xl gap-0 overflow-hidden p-0 sm:max-w-4xl">
        <DialogHeader className="sr-only">
          <DialogTitle>설정</DialogTitle>
        </DialogHeader>

        <aside className="bg-sidebar border-border flex w-44 shrink-0 flex-col border-r sm:w-60">
          <div className="p-3 pb-1">
            <SearchInput
              value={query}
              onValueChange={setQuery}
              placeholder="설정 검색"
              aria-label="설정 검색"
              className="[&_input]:h-9"
            />
          </div>
          <nav className="flex flex-1 flex-col gap-3 overflow-y-auto p-3 pt-2">
            {groups.map((group) => (
              <div key={group.label} className="flex flex-col gap-1">
                <span className="text-muted-foreground px-2 text-xs font-medium">
                  {group.label}
                </span>
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSection(item.id)}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                      section === item.id
                        ? 'bg-accent text-accent-foreground font-medium'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                    )}
                  >
                    <item.icon className="size-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                    {section === item.id && <Check className="ml-auto size-3.5 shrink-0" />}
                  </button>
                ))}
              </div>
            ))}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex h-14 shrink-0 items-center px-6 text-base font-semibold">
            {SECTION_LABEL[section]}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
            {section === 'general' && <GeneralSection />}
            {section === 'account' && <AccountSection />}
            {section === 'ai' && isAdmin && <LlmSettingsSection />}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
