import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import {
  Building2,
  CalendarRange,
  CircleDot,
  ClipboardCheck,
  FileDiff,
  FileText,
  FolderKanban,
  HardHat,
  Info,
  LayoutDashboard,
  Link2,
  MessageSquare,
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Pin,
  RefreshCw,
  ScrollText,
  Trash2,
  Upload,
  Waypoints,
  Wrench,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from '@/components/ui/sidebar';
import { useAuth } from '@/features/auth/auth-context';
import { UserMenu } from '@/components/layout/user-menu';
import { api } from '@/lib/http';
import { cn } from '@/lib/utils';
import { useAsync } from '@/lib/use-async';
import type { ConversationResponse, PageResponse, Role } from '@/types/api';

/** AI 질문은 발주사 전용 — 용역사는 LLM 기능을 쓰지 않는다. */
const ASK_ROLES: Role[] = ['CLIENT'];

/** 용역사에게 감출 메뉴에 붙인다. 용역사는 사업 정보·연동·동기화 이력만 본다. */
const EXCEPT_CONTRACTOR: Role[] = ['SUPER_ADMIN', 'CLIENT'];

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  roles?: Role[];
}

interface NavGroup {
  label: string | null;
  items: NavItem[];
}

/** 프로젝트를 열지 않은 상태의 메뉴. */
const GLOBAL_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [{ to: '/projects', label: '사업 목록', icon: FolderKanban }],
  },
  {
    label: '관리',
    items: [
      { to: '/admin/organizations', label: '발주사', icon: Building2, roles: ['SUPER_ADMIN'] },
      { to: '/admin/contractors', label: '용역사 계정', icon: HardHat, roles: ['SUPER_ADMIN'] },
      { to: '/admin/audit', label: '감사 로그', icon: ScrollText, roles: ['SUPER_ADMIN'] },
    ],
  },
];

/**
 * 프로젝트 메뉴. 표준(ISO 29110) 목차가 아니라 발주사 직원이 던지는 질문 순서로 배열한다.
 * PRD §4.0 — 상시 메뉴에는 모니터링 화면만 두고, 연 1~2회 하는 행정 작업과
 * 운영 진단 화면은 `사업 설정` 아래로 내린다.
 */
const projectGroups = (base: string): NavGroup[] => [
  {
    label: '현황',
    items: [
      {
        to: `${base}/dashboard`,
        label: '진행 상황',
        icon: LayoutDashboard,
        roles: EXCEPT_CONTRACTOR,
      },
      { to: `${base}/schedule`, label: '일정', icon: CalendarRange, roles: EXCEPT_CONTRACTOR },
      { to: `${base}/issues`, label: '이슈 · 위험', icon: CircleDot, roles: EXCEPT_CONTRACTOR },
      { to: `${base}/traceability`, label: '요구사항', icon: Waypoints, roles: EXCEPT_CONTRACTOR },
      { to: `${base}/changes`, label: '변경 요청', icon: FileDiff, roles: EXCEPT_CONTRACTOR },
      { to: `${base}/corrections`, label: '시정조치', icon: Wrench, roles: EXCEPT_CONTRACTOR },
    ],
  },
  {
    label: '자료',
    items: [
      { to: `${base}/deliverables`, label: '산출물', icon: FileText, roles: EXCEPT_CONTRACTOR },
      { to: `${base}/documents`, label: '자료', icon: Upload, roles: EXCEPT_CONTRACTOR },
    ],
  },
  {
    label: '사업 설정',
    items: [
      { to: base, label: '사업 정보', icon: Info, end: true },
      { to: `${base}/assignments`, label: '용역사 할당', icon: HardHat, roles: ['CLIENT'] },
      { to: `${base}/connections`, label: '도구 연동', icon: Link2 },
      { to: `${base}/collection`, label: '동기화 이력', icon: RefreshCw },
      { to: `${base}/acceptance`, label: '검수', icon: ClipboardCheck, roles: ['CLIENT'] },
    ],
  },
];

/** 새 질문 버튼 + 질문 목록. ax-pms 사이드바(NewQuestionButton + 이 사업의 질문)와 동일한 구성. */
function AskSection({ role, onNavigate }: { role: Role; onNavigate: () => void }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { state, isMobile } = useSidebar();

  const projectId = /^\/p\/([^/]+)/.exec(pathname)?.[1];
  const conversationId = /\/ask\/([^/]+)/.exec(pathname)?.[1];
  const base = projectId ? `/p/${projectId}/ask` : '/ask';
  const canAsk = ASK_ROLES.includes(role);

  // 경로가 바뀔 때 다시 읽는다 — 새 대화를 만들면 URL 이 바뀌므로 목록이 따라온다.
  const conversations = useAsync<PageResponse<ConversationResponse> | null>(
    () =>
      canAsk
        ? api.get<PageResponse<ConversationResponse>>('/conversations?size=50')
        : Promise.resolve(null),
    [canAsk, projectId, conversationId],
  );

  if (!canAsk) return null;

  const collapsed = state === 'collapsed' && !isMobile;
  const list = (conversations.data?.content ?? [])
    .filter((c) => !projectId || c.projectScope.includes(projectId))
    .slice()
    .sort((a, b) => Number(b.pinned) - Number(a.pinned));

  const start = () => {
    void navigate(base);
    onNavigate();
  };

  const remove = async (id: string) => {
    await api.del<void>(`/conversations/${id}`);
    if (id === conversationId) void navigate(base);
    else conversations.reload();
  };

  const togglePin = async (id: string, pinned: boolean) => {
    await api.patch<ConversationResponse>(`/conversations/${id}`, { pinned: !pinned });
    conversations.reload();
  };

  const rename = async (id: string, current: string) => {
    const next = window.prompt('질문 제목', current);
    if (next === null || next.trim().length === 0 || next === current) return;
    await api.patch<ConversationResponse>(`/conversations/${id}`, { title: next.trim() });
    conversations.reload();
  };

  return (
    <>
      <SidebarGroup className={cn('shrink-0 py-0', collapsed && 'items-center')}>
        <button
          type="button"
          onClick={start}
          title="새 질문"
          className={cn(
            'text-brand-accent hover:bg-sidebar-accent flex h-9 items-center text-sm font-medium transition-colors',
            collapsed
              ? 'size-9 shrink-0 justify-center rounded-md'
              : 'w-full gap-3 rounded-full px-3',
          )}
        >
          <MessageSquarePlus className="size-4 shrink-0" />
          {collapsed ? (
            <span className="sr-only">새 질문</span>
          ) : (
            <span className="truncate">새 질문</span>
          )}
        </button>
      </SidebarGroup>

      {/* 가로 여백을 안쪽으로 옮겨 스크롤바가 사이드바 오른쪽 끝에 붙게 한다. */}
      {list.length > 0 && (
        <SidebarGroup className="min-h-0 flex-1 px-0">
          <SidebarGroupLabel className="mx-2 shrink-0">
            <span>{projectId ? '이 프로젝트의 질문' : '최근 질문'}</span>
            <span className="ml-auto font-medium">{list.length}</span>
          </SidebarGroupLabel>
          <SidebarGroupContent className="scrollbar-hover min-h-0 flex-1 overflow-y-auto px-2">
            <SidebarMenu>
              {list.map((c) => (
                <SidebarMenuItem key={c.id}>
                  <SidebarMenuButton asChild tooltip={c.title} isActive={c.id === conversationId}>
                    <Link to={`${base}/${c.id}`} onClick={onNavigate}>
                      <MessageSquare className="size-4 shrink-0" />
                      <span className="truncate">
                        {c.pinned ? '📌 ' : ''}
                        {c.title}
                      </span>
                    </Link>
                  </SidebarMenuButton>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <SidebarMenuAction showOnHover>
                        <span className="sr-only">{c.title} 관리</span>
                        <MoreHorizontal className="size-4" />
                      </SidebarMenuAction>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" side="right">
                      <DropdownMenuItem onSelect={() => void togglePin(c.id, c.pinned)}>
                        <Pin className="size-4" />
                        {c.pinned ? '고정 해제' : '고정'}
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => void rename(c.id, c.title)}>
                        <Pencil className="size-4" />
                        이름 변경
                      </DropdownMenuItem>
                      <DropdownMenuItem variant="destructive" onSelect={() => void remove(c.id)}>
                        <Trash2 className="size-4" />
                        삭제
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>

          {/* 아래가 잘린 게 아니라 이어진다는 표시. 스크롤바를 가리지 않게 겹쳐만 둔다. */}
          <div
            aria-hidden
            className="from-sidebar pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t to-transparent"
          />
        </SidebarGroup>
      )}
    </>
  );
}

export function AppSidebar() {
  const { me } = useAuth();
  const { isMobile, setOpenMobile } = useSidebar();
  const { pathname } = useLocation();
  const role = me?.role;
  if (!role) return null;

  const projectId = /^\/p\/([^/]+)/.exec(pathname)?.[1];
  const groups = (projectId ? projectGroups(`/p/${projectId}`) : GLOBAL_GROUPS)
    .map((group) => ({
      ...group,
      items: group.items.filter((i) => !i.roles || i.roles.includes(role)),
    }))
    .filter((group) => group.items.length > 0);

  const closeOnMobile = () => {
    if (isMobile) setOpenMobile(false);
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <NavLink
          to="/"
          onClick={closeOnMobile}
          title="홈으로"
          className="flex items-center gap-2 px-2 py-1.5 text-base font-semibold"
        >
          <span className="bg-brand text-brand-foreground flex size-5 shrink-0 items-center justify-center rounded-sm text-[9px] font-bold">
            AX
          </span>
          <span className="truncate group-data-[collapsible=icon]:hidden">AX-Link</span>
        </NavLink>
      </SidebarHeader>

      {/* 메뉴는 제자리에 두고 질문 목록만 흐른다 — 스크롤은 AskSection 안쪽이 맡는다. */}
      <SidebarContent className="overflow-hidden">
        {groups.map((group, index) => (
          <SidebarGroup className="shrink-0" key={group.label ?? `group-${index}`}>
            {group.label && <SidebarGroupLabel>{group.label}</SidebarGroupLabel>}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <NavLink to={item.to} end={item.end} onClick={closeOnMobile}>
                      {({ isActive }) => (
                        <SidebarMenuButton asChild isActive={isActive} tooltip={item.label}>
                          <span>
                            <item.icon className="size-4 shrink-0" />
                            <span className="truncate">{item.label}</span>
                          </span>
                        </SidebarMenuButton>
                      )}
                    </NavLink>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
        <AskSection role={role} onNavigate={closeOnMobile} />
      </SidebarContent>

      <SidebarFooter>
        <UserMenu />
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
