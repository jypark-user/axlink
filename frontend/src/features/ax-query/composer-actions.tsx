import { type ReactNode } from 'react';
import { FileText, LayoutDashboard, Plus, Waypoints } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { PanelView } from '@/features/ax-query/resource-panel';

const ITEMS: { view: PanelView; label: string; icon: typeof Plus }[] = [
  { view: 'dashboard', label: '진행 상황 펴기', icon: LayoutDashboard },
  { view: 'traceability', label: '요구사항 추적 펴기', icon: Waypoints },
  { view: 'deliverables', label: '산출물 목록 펴기', icon: FileText },
];

/** 컴포저의 + 버튼. 자주 보는 화면을 오른쪽 자료 시트에 편다. */
export function ComposerActions({
  targetName,
  onOpenScreen,
}: {
  targetName: string | null;
  onOpenScreen: (view: PanelView) => void;
}): ReactNode {
  if (!targetName) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          title="자주 쓰는 것"
          className="text-muted-foreground rounded-full"
        >
          <span className="sr-only">자주 쓰는 것</span>
          <Plus className="size-5" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent side="top" align="start" className="w-64">
        <DropdownMenuLabel className="win-label font-normal">{targetName} 자료</DropdownMenuLabel>
        {ITEMS.map((item) => (
          <DropdownMenuItem key={item.view} onSelect={() => onOpenScreen(item.view)}>
            <item.icon className="text-muted-foreground size-4 shrink-0" />
            {item.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
